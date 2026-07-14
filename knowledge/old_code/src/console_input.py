from __future__ import annotations

from pathlib import Path

CANCEL_HINT = "(leave blank to cancel)"


def _prompt(message: str) -> str:
    """Read one line from the console, converting abort signals to a clean exit.

    ``EOFError`` (no console / piped-and-exhausted stdin) and ``KeyboardInterrupt``
    (Ctrl-C) both raise ``SystemExit`` so prompts never hang or dump a traceback.
    """
    import sys

    try:
        return input(message)
    except EOFError:
        sys.exit("\nNo console input available — exiting.")
    except KeyboardInterrupt:
        sys.exit("\nCancelled — exiting.")


def _clean(raw: str) -> str:
    """Trim whitespace and surrounding quotes pasted from a file explorer."""
    return raw.strip().strip('"').strip("'")


def pick_input_path(validate_fn) -> Path | None:
    """Prompt for a valid input CSV path, re-asking until valid or cancelled.

    ``validate_fn(path)`` must return a list of error strings (empty = valid).
    Returns ``None`` when the user submits a blank line (cancel).
    """
    while True:
        raw = _clean(_prompt(f"Input CSV path {CANCEL_HINT}: "))
        if not raw:
            return None
        path = Path(raw)
        errors = validate_fn(path)
        if not errors:
            return path
        print("Invalid CSV:")
        for error in errors:
            print(f"  - {error}")


def pick_output_dir() -> Path | None:
    """Prompt for the output base directory. Blank line cancels (returns None)."""
    raw = _clean(_prompt(f"Output base directory {CANCEL_HINT}: "))
    return Path(raw) if raw else None


def pick_directory(title: str, suggested: Path) -> Path | None:
    """Prompt for a directory path, showing ``suggested`` as a hint.

    A blank line returns ``None`` (cancel), matching the previous GUI semantics
    where cancelling a cache picker disables that cache side.
    """
    print(title)
    print(f"  suggested: {suggested}")
    raw = _clean(_prompt(f"  enter path {CANCEL_HINT}: "))
    return Path(raw) if raw else None


def pick_model(default: str, choices: tuple[str, ...]) -> str:
    """Prompt for a Claude model, accepting a list number or the exact name.

    Pressing Enter accepts ``default``. Re-asks on invalid input.
    """
    print("Select Claude inference model:")
    for index, name in enumerate(choices, start=1):
        marker = "  (default)" if name == default else ""
        print(f"  {index}. {name}{marker}")
    while True:
        raw = _clean(_prompt(f"Model number or name [default {default}]: "))
        if not raw:
            return default
        if raw.isdigit():
            number = int(raw)
            if 1 <= number <= len(choices):
                return choices[number - 1]
        elif raw in choices:
            return raw
        print(f"  Invalid selection. Choose 1-{len(choices)} or a valid model name.")


def pick_workers(default: int, lo: int, hi: int) -> int:
    """Prompt for a worker count in ``[lo, hi]``. Enter accepts ``default``."""
    while True:
        raw = _clean(_prompt(f"Max concurrent workers ({lo}-{hi}) [default {default}]: "))
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"  Please enter an integer between {lo} and {hi}.")
            continue
        if lo <= value <= hi:
            return value
        print(f"  Out of range: must be between {lo} and {hi} (got {value}).")


def confirm_no_cache_read(path: Path) -> bool:
    """Ask whether to continue without cache reads for a missing/empty path."""
    print(f"Cache read directory does not exist or has no cache.csv:\n  {path}")
    return confirm_cacheless_run()


def confirm_invalid_cache_read_value(reason: str) -> bool:
    """Ask whether to continue without cache reads for an invalid config value."""
    print("Invalid cache_read config value:")
    print(f"  {reason}")
    return confirm_cacheless_run()


def confirm_cacheless_run() -> bool:
    """Shared confirmation prompt for proceeding with cache reads disabled."""
    print("No cache will be read, so all libraries will be inferred live.")
    while True:
        raw = _clean(_prompt("Continue without cache read? [y/N]: ")).lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("", "n", "no"):
            return False
        print("  Please answer 'y' or 'n'.")
