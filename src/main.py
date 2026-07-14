"""CLI entry: load config, build run dir, run stub worker pool."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from config import REPO_ROOT, Config, load_config
from input_csv import read_components
from pipeline import run_workers
from results_csv import ResultsWriter
from run_dir import create_run_dir, results_csv_name


def run(config: Config) -> Path:
    components = read_components(config.input_file_path)
    out = create_run_dir(config, components)
    extras = list(components[0].extras.keys()) if components else []
    csv_path = out / results_csv_name(config.model, len(components))
    with ResultsWriter(csv_path, extras) as writer:
        asyncio.run(run_workers(config, components, out, writer))
    return out


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    cfg_path = Path(args[0]) if args else REPO_ROOT / "configs" / "default.json"
    out = run(load_config(cfg_path))
    print(out)


if __name__ == "__main__":
    main()
