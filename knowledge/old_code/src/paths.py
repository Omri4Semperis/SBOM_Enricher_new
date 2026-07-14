from __future__ import annotations

import csv
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from config import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_MODEL,
    MODEL_CHOICES,
    REQUIRED_COLUMNS,
    WORKERS_MAX,
    WORKERS_MIN,
)
import console_input


DEFAULT_CACHE_DIRNAME = "cache"
DEFAULT_CACHE_FILENAME = "cache.csv"

# Repo root: two levels up from this file (src/paths.py -> src/ -> <root>).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


def resolve_project_path(value: str | Path) -> Path:
    """Resolve a path that may be absolute or relative to the project root.

    Absolute paths are returned unchanged. Relative paths are anchored to
    ``PROJECT_ROOT`` (not the process's current working directory), so
    behavior is independent of where the tool happens to be invoked from.
    """
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def default_cache_path() -> Path:
    return Path.cwd() / DEFAULT_CACHE_DIRNAME


def cache_csv_path(cache_dir: Path) -> Path:
    return cache_dir / DEFAULT_CACHE_FILENAME


def _resolve_cache_read_path(path: Path) -> Path:
    if path.exists() and not path.is_dir():
        sys.exit(f"Cache read path must be a directory, got file: {path}")
    if not path.exists() or not cache_csv_path(path).exists():
        confirmed = console_input.confirm_no_cache_read(path)
        if not confirmed:
            sys.exit("Cache read directory does not exist or has no cache.csv and was not confirmed — exiting.")
        raise FileNotFoundError
    return path


def _resolve_cache_write_path(path: Path) -> Path:
    if path.exists() and not path.is_dir():
        sys.exit(f"Cache write path must be a directory, got file: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_cache_paths(
    args_cache_read: str | None,
    args_cache_write: str | None,
) -> tuple[Path | None, Path | None]:
    """Resolve cache read/write directory paths.

    When either CLI flag is omitted, ask explicitly for the missing path on the
    console.
    """
    suggested_path = default_cache_path()

    if args_cache_read:
        cache_read = resolve_project_path(args_cache_read)
    else:
        cache_read = console_input.pick_directory(
            "Select cache directory to read",
            suggested_path,
        )

    if args_cache_write:
        cache_write = resolve_project_path(args_cache_write)
    else:
        cache_write = console_input.pick_directory(
            "Select cache directory to write",
            suggested_path,
        )

    try:
        resolved_read = None if cache_read is None else _resolve_cache_read_path(cache_read)
    except FileNotFoundError:
        resolved_read = None
    resolved_write = None if cache_write is None else _resolve_cache_write_path(cache_write)
    return resolved_read, resolved_write


def validate_input_csv(path: Path) -> list[str]:
    """Return a list of validation error strings; empty list means the file is valid."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            headers = set(csv.DictReader(f).fieldnames or [])
    except Exception as exc:
        return [f"Could not read file: {exc}"]

    missing = REQUIRED_COLUMNS - headers
    if missing:
        return [f"Missing required columns: {sorted(missing)}\nFound: {sorted(headers)}"]
    return []


def _dir_safe_run_name(run_name: str) -> str:
    return "".join("_" if ch in '\\\\/:*?\"<>|' else ch for ch in run_name)


def _count_csv_rows(path: Path) -> int:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return sum(1 for _ in reader)


def _model_name_short(model: str) -> str:
    """Build a short, version-preserving model label for file/folder names.

    e.g. "claude-opus-4-7" -> "ClaudeOpu-4-7", "claude-sonnet-5" -> "ClaudeSon-5".
    Models that don't match "claude-<family>-<major>[-<minor>]" fall back to a
    capitalized, alphanumeric-only truncation of the raw model id.
    """
    match = re.fullmatch(r"claude-([a-z]+)-(\d+)(?:-(\d+))?", model)
    if match is None:
        alnum = "".join(ch for ch in model if ch.isalnum())
        return (alnum or "model").capitalize()[:8]
    family, major, minor = match.groups()
    version = major if minor is None else f"{major}-{minor}"
    return f"Claude{family[:3].capitalize()}-{version}"


def make_results_csv_name(model: str, num_rows: int, run_name: str | None = None) -> str:
    """Build results CSV filename as results_<model_short>_<num_rows>[_<run_name>].csv."""
    filename = f"results_{_model_name_short(model)}_{num_rows}"
    if run_name is not None:
        filename = f"{filename}_{_dir_safe_run_name(run_name)}"
    return f"{filename}.csv"


def make_enriched_csv_name(input_path: Path) -> str:
    return f"{input_path.stem}_enriched.csv"


def create_run_dir(
    input_path: Path,
    output_base: Path,
    model: str,
    run_name: str | None = None,
) -> Path:
    """Create the timestamped run directory and snapshot the input CSV into it.

    Returns the created run directory
    (``<output_base>/<timestamp>_<model_short>_<num_rows>[_<run_name>]``).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_short = _model_name_short(model)
    num_rows = _count_csv_rows(input_path)
    dir_name = f"{timestamp}_{model_short}_{num_rows}"
    if run_name is not None:
        dir_name = f"{dir_name}_{_dir_safe_run_name(run_name)}"
    output_dir = output_base / dir_name
    input_snapshot_dir = output_dir / "input"
    input_snapshot_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(input_path, input_snapshot_dir / input_path.name)
    return output_dir


def resolve_paths(
    args_input: str | None,
    args_output: str | None,
    args_model: str,
    args_run_name: str | None = None,
) -> tuple[Path, Path]:
    """Resolve and validate the input CSV and output directory.

    Falls back to console prompts when CLI args are not provided.
    Returns (input_csv_path, timestamped_output_dir).
    """
    if args_input:
        input_path = resolve_project_path(args_input)
        errors = validate_input_csv(input_path)
        if errors:
            sys.exit("Input CSV validation failed:\n" + "\n".join(errors))
    else:
        input_path = console_input.pick_input_path(validate_input_csv)
        if input_path is None:
            sys.exit("No input file selected — exiting.")

    if args_output:
        output_base = resolve_project_path(args_output)
    else:
        output_base = console_input.pick_output_dir()
        if output_base is None:
            sys.exit("No output directory selected — exiting.")

    output_dir = create_run_dir(input_path, output_base, args_model, args_run_name)

    return input_path, output_dir


def resolve_model(args_model: str | None) -> str:
    """Resolve the effective Claude inference model.

    If ``args_model`` was provided on the CLI, use it (argparse already
    validated it against ``MODEL_CHOICES``). Otherwise, prompt the user on the
    console with the default pre-selected.
    """
    if args_model is not None:
        return args_model
    return console_input.pick_model(DEFAULT_MODEL, MODEL_CHOICES)


def _default_workers_for_input(input_csv: Path) -> int:
    line_count = 0
    with open(input_csv, encoding="utf-8") as f:
        for line_count, _line in enumerate(f, start=1):
            pass
    return max(WORKERS_MIN, min(line_count, DEFAULT_MAX_WORKERS))


def resolve_workers(
    args_workers: int | None,
    input_csv: Path,
    use_defaults: bool = False,
) -> int:
    """Resolve the effective worker count.

    If ``args_workers`` was provided on the CLI, argparse already validated
    it against ``[WORKERS_MIN, WORKERS_MAX]``. When ``use_defaults`` is set,
    the computed default is used without prompting. Otherwise, prompt the user
    on the console with the computed default pre-selected.
    """
    if args_workers is not None:
        return args_workers
    default_workers = _default_workers_for_input(input_csv)
    if use_defaults:
        return default_workers
    return console_input.pick_workers(default_workers, WORKERS_MIN, WORKERS_MAX)
