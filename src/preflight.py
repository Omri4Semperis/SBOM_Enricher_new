"""Startup dual-provider connectivity preflight (fail-fast)."""

from __future__ import annotations

import logging
import subprocess
import time

from azure.identity import DefaultAzureCredential

from config import Config
from gpt41_client import AZURE_TOKEN_SCOPE

# Deterministic backoffs between attempts (no jitter): 2s, 4s, 6s → 4 tries.
BACKOFFS = (2.0, 4.0, 6.0)
ATTEMPTS = len(BACKOFFS) + 1


def _probe_claude(model: str) -> None:
    """Trivial Claude CLI call; raises on non-zero exit."""
    proc = subprocess.run(
        ["claude", "-p", "reply with the single word ok", "--model", model],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = err[0] if err else f"exit {proc.returncode}"
        raise RuntimeError(f"claude probe failed: {detail}")


def _probe_azure() -> None:
    """Acquire an Azure AD token; raises if credential chain fails."""
    logging.getLogger("azure.identity").setLevel(logging.CRITICAL)
    credential = DefaultAzureCredential()
    try:
        credential.get_token(AZURE_TOKEN_SCOPE)
    finally:
        close = getattr(credential, "close", None)
        if callable(close):
            close()


def _retry(probe, label: str) -> None:
    last: BaseException | None = None
    for i in range(ATTEMPTS):
        try:
            probe()
            return
        except BaseException as e:  # noqa: BLE001 — any probe failure retries
            last = e
            if i < ATTEMPTS - 1:
                time.sleep(BACKOFFS[i])
    detail = str(last).splitlines()[0].strip() if last else "unknown"
    raise SystemExit(
        f"Preflight failed ({label}) after {ATTEMPTS} attempts: {detail}"
    ) from None


def preflight(config: Config) -> None:
    """Probe Claude + Azure before workers. Raises SystemExit on failure."""
    _retry(lambda: _probe_claude(config.model), "claude")
    _retry(_probe_azure, "azure")
