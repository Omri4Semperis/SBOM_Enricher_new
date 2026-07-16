"""Claude CLI client for license inference and web copyright fallback."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from pricing import CallMeta
from prompts import copyright_web_prompt, license_prompt
from retry import with_retries

LICENSE_KEYS = ("license_name", "license_code_url", "reasoning")
COPYRIGHT_KEYS = ("copyright", "reasoning")
CLAUDE_TIMEOUT_S = 1200.0


class TransientFailure(Exception):
    pass


class ParseFailure(Exception):
    pass


class HardFailure(Exception):
    pass


def _classify(exc: BaseException) -> str:
    if isinstance(exc, HardFailure):
        return "hard"
    if isinstance(exc, ParseFailure):
        return "parse"
    if isinstance(exc, TransientFailure):
        return "transient"
    return "transient"


def _unknown_license(reason: str) -> dict:
    return {
        "license_name": "UNKNOWN",
        "license_code_url": "",
        "reasoning": reason,
    }


def _unknown_copyright(reason: str) -> dict:
    return {"copyright": "UNKNOWN", "reasoning": reason}


def _parse_cli_stdout(stdout: bytes, required_keys: tuple[str, ...]) -> dict:
    try:
        data = json.loads(stdout.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ParseFailure(f"invalid JSON wrapper: {e}") from e

    payload = data.get("structured_output")
    if payload is None:
        payload = data.get("result")

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as e:
            raise ParseFailure(f"result is not JSON: {e}") from e

    if not isinstance(payload, dict):
        raise ParseFailure("missing structured_output/result object")

    if any(k not in payload for k in required_keys):
        raise ParseFailure(f"contract keys missing: {sorted(payload)}")

    return {k: str(payload[k]) for k in required_keys}


async def _claude_once(
    prompt: str, model: str, schema: dict, meta: CallMeta, required_keys: tuple[str, ...]
) -> dict:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        model,
        "--allowedTools",
        "WebSearch,WebFetch",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path.home()),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CLAUDE_TIMEOUT_S
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise HardFailure(f"claude timed out after {CLAUDE_TIMEOUT_S:.0f}s") from exc
    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        low = err.lower()
        if any(code in low for code in ("401", "403", "404")):
            raise HardFailure(f"claude hard failure ({proc.returncode}): {err[:200]}")
        raise TransientFailure(f"claude exit {proc.returncode}: {err[:200]}")
    raw = stdout.decode(errors="replace")
    try:
        wrapper = json.loads(raw)
        cost = wrapper.get("total_cost_usd") if isinstance(wrapper, dict) else None
    except json.JSONDecodeError:
        cost = None
    meta.add_call(cost_usd=cost if isinstance(cost, (int, float)) else None, raw=raw)
    return _parse_cli_stdout(stdout, required_keys)


async def infer_license(
    purl: str, lib_name: str, version: str, model: str
) -> tuple[dict, CallMeta]:
    """Call Claude; return ({license_name, license_code_url, reasoning}, CallMeta).

    On exhausted retries or hard failure: license_name UNKNOWN, empty URL.
    """
    prompt, schema = license_prompt(purl, lib_name, version)
    attempts = {"n": 0}
    meta = CallMeta()

    async def once() -> dict:
        attempts["n"] += 1
        return await _claude_once(prompt, model, schema, meta, LICENSE_KEYS)

    try:
        result = await with_retries(once, classify=_classify)
    except HardFailure as e:
        result = _unknown_license(f"hard failure: {e}")
    except (TransientFailure, ParseFailure) as e:
        result = _unknown_license(f"retries exhausted: {e}")
    except Exception as e:  # noqa: BLE001 — fail closed per component
        result = _unknown_license(f"error: {e}")

    result["attempts"] = attempts["n"]
    return result, meta


async def infer_copyright_web(
    purl: str, lib_name: str, version: str, model: str
) -> tuple[dict, CallMeta]:
    """Call Claude for web copyright; return ({copyright, reasoning}, CallMeta).

    On exhausted retries or hard failure: copyright UNKNOWN. Always returns meta.
    """
    prompt, schema = copyright_web_prompt(purl, lib_name, version)
    attempts = {"n": 0}
    meta = CallMeta()

    async def once() -> dict:
        attempts["n"] += 1
        return await _claude_once(prompt, model, schema, meta, COPYRIGHT_KEYS)

    try:
        result = await with_retries(once, classify=_classify)
    except HardFailure as e:
        result = _unknown_copyright(f"hard failure: {e}")
    except (TransientFailure, ParseFailure) as e:
        result = _unknown_copyright(f"retries exhausted: {e}")
    except Exception as e:  # noqa: BLE001 — fail closed per component
        result = _unknown_copyright(f"error: {e}")

    result["attempts"] = attempts["n"]
    return result, meta
