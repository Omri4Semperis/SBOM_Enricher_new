from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from config import MODEL_CHOICES, WORKERS_MAX, WORKERS_MIN
import console_input
import paths


REQUIRED_KEYS: frozenset[str] = frozenset(
    {"input_csv", "output_base", "model", "workers"}
)
OPTIONAL_KEYS: frozenset[str] = frozenset(
    {
        "run_name",
        "cache_read",
        "cache_write",
        "force_license_inference",
        "force_copyright_extraction",
    }
)
ALLOWED_KEYS: frozenset[str] = REQUIRED_KEYS | OPTIONAL_KEYS


@dataclass(frozen=True)
class RunConfig:
    """Fully-specified run parameters loaded from a JSON config file."""

    input_csv: Path | None
    output_base: Path
    run_name: str | None
    model: str
    workers: int
    force_license_inference: bool
    force_copyright_extraction: bool
    cache_read: Path | None
    cache_write: Path | None


def _fail(config_path: Path, message: str) -> "RunConfig":
    sys.exit(f"Invalid config file {config_path}:\n  {message}")


def _resolved_path(config_path: Path, key: str, value: object) -> Path:
    """Validate and resolve a path value: absolute as-is, or relative to the project root."""
    if not isinstance(value, str) or not value.strip():
        _fail(config_path, f"'{key}' must be a non-empty string path.")
    return paths.resolve_project_path(value)  # type: ignore[arg-type]


def _optional_run_name(config_path: Path, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(config_path, f"'run_name' must be a string when provided, got: {value!r}")
    run_name = value.strip()
    if not run_name:
        _fail(config_path, "'run_name' must be a non-empty string when provided.")
    return run_name


def load_run_config(config_path: Path, *, require_input_csv: bool = True) -> RunConfig:
    """Load and fully validate a JSON run-config file.

    Validation is strict for schema/type/path correctness (bad JSON, missing or
    unknown keys, invalid model/workers, non-absolute paths, and invalid input
    CSV). For a ``cache_read`` directory that is missing or lacks ``cache.csv``,
    the user is prompted to continue without cache reads or abort.
    """
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        sys.exit(f"Could not read config file {config_path}: {exc}")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        sys.exit(f"Invalid config file {config_path}: not valid JSON ({exc}).")

    if not isinstance(data, dict):
        sys.exit(f"Invalid config file {config_path}: top level must be a JSON object.")

    required_keys = REQUIRED_KEYS if require_input_csv else (REQUIRED_KEYS - {"input_csv"})

    keys = set(data.keys())
    missing = required_keys - keys
    if missing:
        _fail(config_path, f"missing required keys: {sorted(missing)}")
    unknown = keys - ALLOWED_KEYS
    if unknown:
        _fail(config_path, f"unknown keys: {sorted(unknown)} (allowed: {sorted(ALLOWED_KEYS)})")

    input_csv: Path | None = None
    if "input_csv" in data:
        input_csv = _resolved_path(config_path, "input_csv", data["input_csv"])
        input_errors = paths.validate_input_csv(input_csv)
        if input_errors:
            _fail(config_path, "input_csv is not valid:\n  " + "\n  ".join(input_errors))

    output_base = _resolved_path(config_path, "output_base", data["output_base"])
    run_name = _optional_run_name(config_path, data.get("run_name"))

    model = data["model"]
    if model not in MODEL_CHOICES:
        _fail(
            config_path,
            f"'model' must be one of {list(MODEL_CHOICES)}, got: {model!r}",
        )

    workers = data["workers"]
    if not isinstance(workers, int) or isinstance(workers, bool):
        _fail(config_path, f"'workers' must be an integer, got: {workers!r}")
    if not WORKERS_MIN <= workers <= WORKERS_MAX:
        _fail(
            config_path,
            f"'workers' must be between {WORKERS_MIN} and {WORKERS_MAX}, got: {workers}",
        )

    force_license_inference = data.get("force_license_inference", False)
    if not isinstance(force_license_inference, bool):
        _fail(
            config_path,
            "'force_license_inference' must be a boolean when provided, "
            f"got: {force_license_inference!r}",
        )

    force_copyright_extraction = data.get("force_copyright_extraction", False)
    if not isinstance(force_copyright_extraction, bool):
        _fail(
            config_path,
            "'force_copyright_extraction' must be a boolean when provided, "
            f"got: {force_copyright_extraction!r}",
        )

    cache_read = _resolve_config_cache_read(
        config_path,
        data.get("cache_read"),
        was_provided="cache_read" in data,
    )
    cache_write = _resolve_config_cache_write(config_path, data.get("cache_write"))

    return RunConfig(
        input_csv=input_csv,
        output_base=output_base,
        run_name=run_name,
        model=model,
        workers=workers,
        force_license_inference=force_license_inference,
        force_copyright_extraction=force_copyright_extraction,
        cache_read=cache_read,
        cache_write=cache_write,
    )


def _resolve_config_cache_read(config_path: Path, value: object, *, was_provided: bool) -> Path | None:
    if value is None:
        if not was_provided:
            return None
        confirmed = console_input.confirm_invalid_cache_read_value(
            "'cache_read' was set to null/None."
        )
        if not confirmed:
            _fail(config_path, "invalid cache_read value was not confirmed")
        return None

    if not isinstance(value, str):
        confirmed = console_input.confirm_invalid_cache_read_value(
            f"'cache_read' must be a string path when provided, got: {value!r}"
        )
        if not confirmed:
            _fail(config_path, "invalid cache_read value was not confirmed")
        return None

    if not value.strip():
        confirmed = console_input.confirm_invalid_cache_read_value(
            "'cache_read' was empty or whitespace."
        )
        if not confirmed:
            _fail(config_path, "invalid cache_read value was not confirmed")
        return None

    path = paths.resolve_project_path(value)

    if not path.is_dir() or not paths.cache_csv_path(path).exists():
        confirmed = console_input.confirm_no_cache_read(path)
        if not confirmed:
            _fail(
                config_path,
                "cache_read directory does not exist or has no cache.csv and was not confirmed",
            )
        return None
    return path


def _resolve_config_cache_write(config_path: Path, value: object) -> Path | None:
    if value is None:
        return None
    path = _resolved_path(config_path, "cache_write", value)
    if path.exists() and not path.is_dir():
        _fail(config_path, f"cache_write path must be a directory, got file: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path
