"""Create the per-run output directory tree and naming helpers."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from config import Config
from input_csv import Component

_CLAUDE_MODEL = re.compile(r"claude-([a-z]+)-(\d+)(?:-(\d+))?")


def model_short(model: str) -> str:
    """Short label for dir/file names. e.g. claude-opus-4-8 -> ClaudeOpu-4-8."""
    match = _CLAUDE_MODEL.fullmatch(model)
    if match is None:
        alnum = "".join(ch for ch in model if ch.isalnum())
        return (alnum or "model").capitalize()[:8]
    family, major, minor = match.groups()
    version = major if minor is None else f"{major}-{minor}"
    return f"Claude{family[:3].capitalize()}-{version}"


def results_csv_name(model: str, n_components: int) -> str:
    return f"results_{model_short(model)}_{n_components}.csv"


def create_run_dir(config: Config, components: list[Component]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short = model_short(config.model)
    n = len(components)
    run_dir = config.output_base_path / f"{timestamp}_{short}_{n}"
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "licenses").mkdir()
    shutil.copy2(config.input_file_path, input_dir / config.input_file_path.name)
    snapshot = {
        "input_file_path": str(config.input_file_path),
        "output_base_path": str(config.output_base_path),
        "run_name": config.run_name,
        "model": config.model,
        "workers": config.workers,
        "cache_read": str(config.cache_read) if config.cache_read else None,
        "cache_write": str(config.cache_write) if config.cache_write else None,
    }
    (input_dir / "config.json").write_text(
        json.dumps(snapshot, indent=2) + "\n", encoding="utf-8"
    )
    for comp in components:
        comp_dir = run_dir / "per_component" / comp.slug
        comp_dir.mkdir(parents=True, exist_ok=True)
        meta = {"component_name": comp.component_name, "purl": comp.purl}
        (comp_dir / "meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
    return run_dir
