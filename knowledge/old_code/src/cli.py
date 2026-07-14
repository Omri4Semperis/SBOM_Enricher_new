from __future__ import annotations

import argparse

from config import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_MODEL,
    MODEL_CHOICES,
    WORKERS_MAX,
    WORKERS_MIN,
)


def _workers_type(value: str) -> int:
    """argparse type for --workers: int in [WORKERS_MIN, WORKERS_MAX]."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"workers must be an integer, got {value!r}")
    if not WORKERS_MIN <= n <= WORKERS_MAX:
        raise argparse.ArgumentTypeError(
            f"workers must be between {WORKERS_MIN} and {WORKERS_MAX} (got {n})"
        )
    return n


def _run_name_type(value: str) -> str:
    """argparse type for --run-name: non-empty string after trimming."""
    run_name = value.strip()
    if not run_name:
        raise argparse.ArgumentTypeError("run_name must be a non-empty string")
    return run_name


# CLI flags (other than --config / --use-defaults) that select run parameters.
# Used to enforce mode exclusivity.
_PARAM_FLAGS: tuple[tuple[str, str], ...] = (
    ("input", "--input"),
    ("output", "--output"),
    ("run_name", "--run-name"),
    ("cache_read", "--cache-read"),
    ("cache_write", "--cache-write"),
    ("workers", "--workers"),
    ("model", "--model"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query Claude for library licenses and write results to CSV."
    )
    parser.add_argument(
        "--config",
        metavar="JSON",
        help=(
            "Path to a JSON file specifying every run parameter. Runs without any "
            "console prompts. Mutually exclusive with all other flags; the file is "
            "copied into the run's output directory for the record."
        ),
    )
    parser.add_argument(
        "--use-defaults",
        action="store_true",
        help=(
            "Only prompt for the necessary parameters (input, output, model, and "
            "cache directories); use the computed default for --workers. Cannot be "
            "combined with --workers or --config."
        ),
    )
    parser.add_argument("--input", metavar="CSV", help="Path to input CSV file")
    parser.add_argument("--output", metavar="DIR", help="Base directory for output")
    parser.add_argument(
        "--run-name",
        metavar="NAME",
        type=_run_name_type,
        default=None,
        help=(
            "Optional label appended to the timestamped output directory name, "
            "for example 20260623_150059_my-run."
        ),
    )
    parser.add_argument(
        "--cache-read",
        metavar="DIR",
        help=(
            "Path to the cache directory to read from. If omitted, the path is requested "
            "explicitly via a console prompt."
        ),
    )
    parser.add_argument(
        "--cache-write",
        metavar="DIR",
        help=(
            "Path to the cache directory to write to. If omitted, the path is requested "
            "explicitly via a console prompt."
        ),
    )
    # Default is None (not DEFAULT_MAX_WORKERS) so main.py can distinguish
    # "user omitted --workers" from "user explicitly chose the default": when
    # omitted, a console prompt asks for the value.
    parser.add_argument(
        "--workers",
        metavar="N",
        type=_workers_type,
        default=None,
        help=(
            f"Max concurrent Claude workers ({WORKERS_MIN}-{WORKERS_MAX}). "
            f"If omitted, a console prompt asks for the value (default: {DEFAULT_MAX_WORKERS})."
        ),
    )
    # Default is None (not DEFAULT_MODEL) so main.py can distinguish "user
    # omitted --model" from "user explicitly chose the default": when
    # omitted, a console prompt asks for the value.
    parser.add_argument(
        "--model",
        metavar="NAME",
        choices=list(MODEL_CHOICES),
        default=None,
        help=(
            "Claude inference model name. One of: "
            f"{', '.join(MODEL_CHOICES)}. If omitted, a console prompt asks for the value "
            f"(default selection: {DEFAULT_MODEL})."
        ),
    )
    return parser


def validate_modes(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Enforce mutual exclusivity between --config, --use-defaults and param flags."""
    if args.config is not None:
        conflicting = [flag for attr, flag in _PARAM_FLAGS if getattr(args, attr) is not None]
        if args.use_defaults:
            conflicting.append("--use-defaults")
        if conflicting:
            parser.error(
                "--config cannot be combined with other flags; remove: "
                + ", ".join(conflicting)
            )
        return

    if args.use_defaults and args.workers is not None:
        parser.error(
            "--use-defaults defaults the worker count; remove --workers (or drop --use-defaults)."
        )


def parse_args() -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args()
    validate_modes(parser, args)
    return args
