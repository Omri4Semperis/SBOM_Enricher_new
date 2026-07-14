"""Load and validate configs/default.json (and same-shaped JSON files)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MODEL_CHOICES: tuple[str, ...] = (
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
)


@dataclass(frozen=True)
class Config:
    input_file_path: Path
    output_base_path: Path
    run_name: str | None
    model: str
    workers: int
    cache_read: Path | None
    cache_write: Path | None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SystemExit(f"expected string or null, got {type(value).__name__}")
    return value if value.strip() else None


def _required_str(value: object, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing or empty required field: {key}")
    return value


def _resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def _optional_path(value: object) -> Path | None:
    s = _optional_str(value)
    return _resolve(s) if s is not None else None


def load_config(path: Path | str) -> Config:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("config root must be a JSON object")

    model = _required_str(raw.get("model"), "model")
    if model not in MODEL_CHOICES:
        raise SystemExit(f"unknown model: {model!r}")

    workers = raw.get("workers")
    if not isinstance(workers, int) or isinstance(workers, bool) or not (1 <= workers <= 30):
        raise SystemExit(f"workers must be an int in [1, 30], got {workers!r}")

    return Config(
        input_file_path=_resolve(_required_str(raw.get("input_file_path"), "input_file_path")),
        output_base_path=_resolve(_required_str(raw.get("output_base_path"), "output_base_path")),
        run_name=_optional_str(raw.get("run_name")),
        model=model,
        workers=workers,
        cache_read=_optional_path(raw.get("cache_read")),
        cache_write=_optional_path(raw.get("cache_write")),
    )
