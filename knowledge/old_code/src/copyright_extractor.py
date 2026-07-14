"""Second-step copyright extractor powered by gpt-4.1.

This module is intentionally isolated from orchestration and output formatting.
It accepts plain license text, retries transient/unparsable model calls, and
fails closed to UNKNOWN with stable machine-readable reasons.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

import client
import config
from cost_tracking import CallMeta
from gpt41_client import Gpt41Client
from response_parser import CopyrightResult, extract_json


# Generic license templates leave the copyright line unfilled, wrapping the
# year/holder in <...>, [...], or {...} placeholders — e.g.
# "Copyright (c) <year> <copyright holders>",
# "Copyright [yyyy] [name of copyright owner]",
# "Copyright (c) [year] [fullname]".
# A real notice names a concrete holder (a year is optional), so a bracketed
# token wrapping one of these placeholder keywords marks the text as boilerplate
# rather than the project's own copyright.
_PLACEHOLDER_TOKEN_RE = re.compile(
    r"[<\[{][^<>\[\]{}]*"
    r"(?:year|yyyy|name|author|owner|holder|fullname|full[ _-]?name|"
    r"organi[sz]ation|copyright|date)"
    r"[^<>\[\]{}]*[>\]}]",
    re.IGNORECASE,
)


def is_placeholder_copyright(text: str) -> bool:
    """Return True if ``text`` is an unfilled license-template copyright line.

    Detects placeholder tokens such as ``<year>``, ``[yyyy]``,
    ``<copyright holders>``, or ``[name of copyright owner]`` that generic
    license templates use in place of a real holder name. When True, the
    extracted text is boilerplate and must not be treated as a real copyright
    notice — UNKNOWN is preferable to emitting placeholder text.
    """
    return bool(_PLACEHOLDER_TOKEN_RE.search(text))


def _parse_copyright_response(raw: str) -> tuple[str, str]:
    """Parse extractor JSON and return (copyright_text, reasoning)."""
    snippet = extract_json(raw)
    if not snippet:
        raise ValueError("no JSON object found in copyright extractor response")
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in copyright extractor response: {exc}") from exc

    copyright_text = str(data.get("copyright", "")).strip()
    reasoning = str(data.get("reasoning", "")).strip()
    if not copyright_text:
        raise ValueError("missing 'copyright' in copyright extractor response")
    return copyright_text, reasoning


async def extract_copyright(
    client: Gpt41Client,
    sem: asyncio.Semaphore,
    license_text: str | None,
) -> CopyrightResult:
    """Extract copyright from license text.

    Returns CopyrightResult with stable reasons, raw response, elapsed time,
    attempt count, and call metadata when usage information is available.
    """
    if license_text is None:
        return CopyrightResult(
            copyright=config.COPYRIGHT_UNKNOWN,
            reason=config.COPYRIGHT_REASON_NO_FILE,
            raw_response="",
            elapsed_s=0.0,
            attempt_count=0,
            extract_meta=None,
        )

    if not str(license_text).strip():
        return CopyrightResult(
            copyright=config.COPYRIGHT_UNKNOWN,
            reason=config.COPYRIGHT_REASON_EMPTY_FILE,
            raw_response="",
            elapsed_s=0.0,
            attempt_count=0,
            extract_meta=None,
        )

    user_prompt = config.COPYRIGHT_USER_TEMPLATE.format(license_text=license_text)
    start = time.monotonic()
    last_raw = ""
    last_error = ""

    for attempt in range(1, config.COPYRIGHT_MAX_ATTEMPTS + 1):
        try:
            async with sem:
                raw, usage = await client.complete(
                    config.COPYRIGHT_SYSTEM_PROMPT,
                    user_prompt,
                    max_completion_tokens=config.COPYRIGHT_MAX_COMPLETION_TOKENS,
                    temperature=0.0,
                )
            last_raw = raw
            copyright_text, _ = _parse_copyright_response(raw)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < config.COPYRIGHT_MAX_ATTEMPTS:
                await asyncio.sleep(config.COPYRIGHT_BACKOFF_BASE_S * attempt)
            continue

        elapsed = time.monotonic() - start
        meta = CallMeta(
            model=config.GPT41_MODEL,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cache_read_tokens=usage.get("cache_read_tokens"),
            cost_usd=config.compute_cost(
                model=config.GPT41_MODEL,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_tokens", 0),
            ),
            elapsed_s=elapsed,
        )

        if copyright_text.upper() == config.COPYRIGHT_UNKNOWN:
            return CopyrightResult(
                copyright=config.COPYRIGHT_UNKNOWN,
                reason=config.COPYRIGHT_REASON_NO_COPYRIGHT_FOUND,
                raw_response=raw,
                elapsed_s=elapsed,
                attempt_count=attempt,
                extract_meta=meta,
            )

        # A generic license template leaves its copyright line unfilled, e.g.
        # "Copyright (c) <year> <copyright holders>". Extracting that verbatim
        # would emit placeholder text as if it were a real notice, so fail
        # closed to UNKNOWN rather than returning something wrong.
        if is_placeholder_copyright(copyright_text):
            return CopyrightResult(
                copyright=config.COPYRIGHT_UNKNOWN,
                reason=config.COPYRIGHT_REASON_PLACEHOLDER,
                raw_response=raw,
                elapsed_s=elapsed,
                attempt_count=attempt,
                extract_meta=meta,
            )

        return CopyrightResult(
            copyright=copyright_text,
            reason=config.COPYRIGHT_REASON_EXTRACTED,
            raw_response=raw,
            elapsed_s=elapsed,
            attempt_count=attempt,
            extract_meta=meta,
        )

    return CopyrightResult(
        copyright=config.COPYRIGHT_UNKNOWN,
        reason=config.COPYRIGHT_REASON_RETRY_EXHAUSTED,
        raw_response=last_raw,
        elapsed_s=time.monotonic() - start,
        attempt_count=config.COPYRIGHT_MAX_ATTEMPTS,
        extract_meta=None,
    )


async def infer_copyright(
    sem: asyncio.Semaphore,
    lib_name: str,
    version: str,
    purl: str,
    model: str,
) -> CopyrightResult:
    """Ask a web-enabled Claude call directly for the copyright holder.

    Last-resort copyright fallback: called only when file-based extraction and
    (for npm) the registry-author fallback have both failed to yield a
    holder. Fails closed to UNKNOWN on any parse error, model UNKNOWN, or
    placeholder/template text -- never invents a holder.
    """
    start = time.monotonic()
    raw, meta = await client.query_claude_copyright(sem, lib_name, version, purl, model)
    elapsed = time.monotonic() - start

    if not raw:
        return CopyrightResult(
            copyright=config.COPYRIGHT_UNKNOWN,
            reason=config.COPYRIGHT_REASON_NO_COPYRIGHT_FOUND,
            raw_response="",
            elapsed_s=elapsed,
            attempt_count=1,
            extract_meta=meta,
        )

    try:
        copyright_text, _ = _parse_copyright_response(raw)
    except ValueError:
        return CopyrightResult(
            copyright=config.COPYRIGHT_UNKNOWN,
            reason=config.COPYRIGHT_REASON_NO_COPYRIGHT_FOUND,
            raw_response=raw,
            elapsed_s=elapsed,
            attempt_count=1,
            extract_meta=meta,
        )

    if copyright_text.upper() == config.COPYRIGHT_UNKNOWN:
        return CopyrightResult(
            copyright=config.COPYRIGHT_UNKNOWN,
            reason=config.COPYRIGHT_REASON_NO_COPYRIGHT_FOUND,
            raw_response=raw,
            elapsed_s=elapsed,
            attempt_count=1,
            extract_meta=meta,
        )

    # Guard against a generic template holder slipping through, same as the
    # file-extraction path: fail closed to UNKNOWN rather than return
    # placeholder text as if it were a real notice.
    if is_placeholder_copyright(copyright_text):
        return CopyrightResult(
            copyright=config.COPYRIGHT_UNKNOWN,
            reason=config.COPYRIGHT_REASON_PLACEHOLDER,
            raw_response=raw,
            elapsed_s=elapsed,
            attempt_count=1,
            extract_meta=meta,
        )

    return CopyrightResult(
        copyright=copyright_text,
        reason=config.COPYRIGHT_REASON_INFERRED,
        raw_response=raw,
        elapsed_s=elapsed,
        attempt_count=1,
        extract_meta=meta,
    )
