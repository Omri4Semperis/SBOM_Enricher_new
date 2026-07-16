"""CLI entry: load config, preflight, run workers, write outputs."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import REPO_ROOT, Config, load_config
from input_csv import read_components
from pipeline import run_workers
from preflight import preflight
from progress import Progress
from results_csv import ExtendedWriter, ResultsWriter, detect_gt_columns, extended_csv_path
from run_dir import create_run_dir, results_csv_name
from runtime_report import write_runtime_report
from scoring import write_score_csv
from summary import build_summary, write_summary


class _FanoutWriter:
    """Write main + extended rows and tick progress (no pipeline edit)."""

    def __init__(
        self,
        main_w: ResultsWriter,
        ext_w: ExtendedWriter,
        progress: Progress,
    ) -> None:
        self._main = main_w
        self._ext = ext_w
        self._progress = progress

    def write_row(self, result) -> None:
        self._main.write_row(result)
        self._ext.write_row(result)
        self._progress.tick()


def run(config: Config) -> Path:
    print(f"input:      {config.input_file_path}", file=sys.stderr)
    print(f"output:     {config.output_base_path}", file=sys.stderr)
    print(f"model:      {config.model}", file=sys.stderr)
    print(f"workers: {config.workers}", file=sys.stderr)
    components = read_components(config.input_file_path)
    print(f"components: {len(components)}", file=sys.stderr)
    print("\nRunning startup checks (Claude + Azure)…\n", file=sys.stderr, flush=True)
    preflight(config)
    out = create_run_dir(config, components)
    print(f"run dir:    {out}", file=sys.stderr)
    extras = list(components[0].extras.keys()) if components else []
    gt_columns = detect_gt_columns(extras)
    csv_path = out / results_csv_name(config.model, len(components))
    ext_path = extended_csv_path(csv_path)
    progress = Progress(len(components))
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    progress.start()
    with (
        ResultsWriter(csv_path, extras) as writer,
        ExtendedWriter(ext_path, extras, out) as extended,
    ):
        fanout = _FanoutWriter(writer, extended, progress)
        results = asyncio.run(
            run_workers(config, components, out, fanout, gt_columns=gt_columns)
        )
    wall = time.perf_counter() - t0
    ended = datetime.now(timezone.utc)
    if gt_columns:
        write_score_csv(out / "score.csv", results, gt_columns)
    write_summary(
        out / "summary.json",
        build_summary(
            config,
            out,
            results,
            started_at=started,
            ended_at=ended,
            wall_seconds=wall,
        ),
    )
    report_path = write_runtime_report(out)
    print(f"report: {report_path}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    cfg_path = Path(args[0]) if args else REPO_ROOT / "configs" / "default.json"
    out = run(load_config(cfg_path))
    print(out)


if __name__ == "__main__":
    main()
