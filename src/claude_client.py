"""Claude CLI client for license inference."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from prompts import license_prompt
from retry import with_retries

REQUIRED_KEYS = ("license_name", "license_code_url", "reasoning")


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


def _unknown(reason: str) -> dict:
    return {
        "license_name": "UNKNOWN",
        "license_code_url": "",
        "reasoning": reason,
    }


def _parse_cli_stdout(stdout: bytes) -> dict:
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

    if any(k not in payload for k in REQUIRED_KEYS):
        raise ParseFailure(f"contract keys missing: {sorted(payload)}")

    return {
        "license_name": str(payload["license_name"]),
        "license_code_url": str(payload["license_code_url"]),
        "reasoning": str(payload["reasoning"]),
    }


async def _claude_once(prompt: str, model: str, schema: dict) -> dict:
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
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        low = err.lower()
        if any(code in low for code in ("401", "403", "404")):
            raise HardFailure(f"claude hard failure ({proc.returncode}): {err[:200]}")
        raise TransientFailure(f"claude exit {proc.returncode}: {err[:200]}")
    return _parse_cli_stdout(stdout)


async def infer_license(
    purl: str, lib_name: str, version: str, model: str
) -> dict:
    """Call Claude; return {license_name, license_code_url, reasoning}.

    On exhausted retries or hard failure: license_name UNKNOWN, empty URL.
    """
    prompt, schema = license_prompt(purl, lib_name, version)
    attempts = {"n": 0}

    async def once() -> dict:
        attempts["n"] += 1
        return await _claude_once(prompt, model, schema)

    try:
        result = await with_retries(once, classify=_classify)
    except HardFailure as e:
        result = _unknown(f"hard failure: {e}")
    except (TransientFailure, ParseFailure) as e:
        result = _unknown(f"retries exhausted: {e}")
    except Exception as e:  # noqa: BLE001 — fail closed per component
        result = _unknown(f"error: {e}")

    result["attempts"] = attempts["n"]
    return result
