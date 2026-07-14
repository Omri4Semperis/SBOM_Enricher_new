from __future__ import annotations

import asyncio
import json
import subprocess
import time
from pathlib import Path

from config import CLAUDE_TIMEOUT_S, build_copyright_query_prompt, build_query_prompt
from cost_tracking import CallMeta


async def _invoke_claude(
    sem: asyncio.Semaphore,
    prompt: str,
    model: str,
) -> tuple[str, CallMeta]:
    """Call `claude -p <prompt> --model <model> --output-format json` and return (stdout_text, CallMeta).

    Returns ("", CallMeta with no cost) on non-zero exit code, or when the call
    exceeds ``CLAUDE_TIMEOUT_S`` (the process is killed and treated as no
    response so a hung web call cannot stall the run).
    """
    async with sem:
        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            "--model", model,
            "--allowedTools", "WebSearch,WebFetch",
            "--output-format", "json",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path.home()),  # neutral cwd so project CLAUDE.md is not loaded
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=CLAUDE_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return "", CallMeta(model=model, elapsed_s=time.monotonic() - start)

    elapsed = time.monotonic() - start
    meta = CallMeta(model=model, elapsed_s=elapsed)

    if proc.returncode != 0:
        return "", meta

    try:
        data = json.loads(stdout.decode())
    except json.JSONDecodeError:
        return "", meta

    text = data.get("result", "")
    meta.cost_usd = data.get("total_cost_usd")

    # If token counts are available, populate them
    if "usage" in data:
        usage = data.get("usage", {})
        meta.input_tokens = usage.get("input_tokens")
        meta.output_tokens = usage.get("output_tokens")
        meta.cache_read_tokens = usage.get("cache_read_input_tokens")
        meta.cache_write_tokens = usage.get("cache_creation_input_tokens")

    return text, meta


async def query_claude(
    sem: asyncio.Semaphore,
    lib_name: str,
    version: str,
    purl: str,
    model: str,
    *,
    need_license: bool = True,
    need_url: bool = True,
) -> tuple[str, CallMeta]:
    """Ask Claude for the license identifier and/or license URL of a package."""
    prompt = build_query_prompt(
        lib_name=lib_name.strip(),
        version=version.strip(),
        purl=purl,
        need_license=need_license,
        need_url=need_url,
    )
    return await _invoke_claude(sem, prompt, model)


async def query_claude_copyright(
    sem: asyncio.Semaphore,
    lib_name: str,
    version: str,
    purl: str,
    model: str,
) -> tuple[str, CallMeta]:
    """Ask Claude directly for a package's copyright holder.

    Last-resort copyright fallback, used only after the LICENSE file and (for
    npm) the registry author have both failed to yield a holder.
    """
    prompt = build_copyright_query_prompt(
        lib_name=lib_name.strip(),
        version=version.strip(),
        purl=purl,
    )
    return await _invoke_claude(sem, prompt, model)
