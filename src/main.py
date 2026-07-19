"""CLI entry: load config, preflight, run workers, write outputs."""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from config import REPO_ROOT, Config, load_config
from enriched_csv import write_enriched_csv
from eventlog import close_event_log, emit, init_event_log
from input_csv import read_components, read_input_rows
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

        self._first_row_seen = False

    def write_row(self, result) -> None:
        self._main.write_row(result)
        self._ext.write_row(result)
        if not self._first_row_seen:
            self._first_row_seen = True
            emit("first_row", slug=result.component.slug)
        self._progress.tick(failed=bool(result.error))


def run(config: Config) -> Path:
    print(f"input:      {config.input_file_path}", file=sys.stderr)
    print(f"output:     {config.output_base_path}", file=sys.stderr)
    print(f"model:      {config.model}", file=sys.stderr)
    print(f"workers:    {config.workers}", file=sys.stderr)
    components = read_components(config.input_file_path)
    print(f"components: {len(components)}", file=sys.stderr)
    print("\nRunning startup checks (Claude + Azure)…\n", file=sys.stderr, flush=True)
    t_pre = time.perf_counter()
    preflight(config)
    preflight_s = time.perf_counter() - t_pre
    out = create_run_dir(config, components)
    print(f"run dir:    {out}", file=sys.stderr)
    init_event_log(out / "events.jsonl", out.name)
    emit(
        "run",
        "start",
        components=len(components),
        model=config.model,
        workers=config.workers,
        input=str(config.input_file_path),
    )
    # Preflight runs before the run dir exists, so it is logged retroactively as
    # a single completed event carrying its measured duration.
    emit("preflight", "end", dur_s=round(preflight_s, 3), status="ok")
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
        emit("workers", "start", n=len(components))
        t_workers = time.perf_counter()
        results = asyncio.run(
            run_workers(config, components, out, fanout, gt_columns=gt_columns)
        )
        emit(
            "workers",
            "end",
            dur_s=round(time.perf_counter() - t_workers, 3),
            n=len(results),
            status="ok",
        )
    wall = time.perf_counter() - t0
    ended = datetime.now(timezone.utc)
    failed = sum(bool(result.error) for result in results)
    if failed:
        print(
            f"{failed}/{len(components)} components failed "
            "(see extended CSV 'error' column)",
            file=sys.stderr,
        )
    fieldnames, rows = read_input_rows(config.input_file_path)
    write_enriched_csv(
        out / "library_approvals_enriched.csv", fieldnames, rows, results
    )
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
    emit("run", "end", dur_s=round(wall, 3), components=len(results), status="ok")
    close_event_log()
    return out


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    cfg_path = Path(args[0]) if args else REPO_ROOT / "configs" / "default.json"
    out = run(load_config(cfg_path))
    print(out)


if __name__ == "__main__":
    main()
