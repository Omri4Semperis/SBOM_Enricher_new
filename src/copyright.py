"""File-only copyright extraction (ADR 0003)."""

from __future__ import annotations

import re

from gpt41_client import Gpt41Client
from pricing import CallMeta
from prompts import copyright_prompt

REQUIRED_KEYS = ("copyright", "reasoning")

_PLACEHOLDER_TOKEN_RE = re.compile(
    r"[<\[{][^<>\[\]{}]*"
    r"(?:year|yyyy|name|author|owner|holder|fullname|full[ _-]?name|"
    r"organi[sz]ation|copyright|date)"
    r"[^<>\[\]{}]*[>\]}]",
    re.IGNORECASE,
)


def _is_placeholder_copyright(text: str) -> bool:
    return bool(_PLACEHOLDER_TOKEN_RE.search(text))


def _unknown(reason: str) -> dict:
    return {"copyright": "UNKNOWN", "reasoning": reason}


async def extract_copyright(license_text: str) -> tuple[dict, CallMeta]:
    """Extract {copyright, reasoning} from LICENSE text via GPT-4.1.

    Placeholder / failure / empty ⇒ copyright UNKNOWN. No fallbacks.
    Returns (payload, CallMeta); empty meta when no billable call was made.
    """
    if not (license_text or "").strip():
        return _unknown("empty license text"), CallMeta()

    system, user = copyright_prompt(license_text)
    meta = CallMeta()
    try:
        data, meta = await Gpt41Client().complete_json(system, user)
    except Exception as e:  # noqa: BLE001 — fail closed per component
        meta = getattr(e, "meta", None) or meta
        return _unknown(f"retries exhausted: {e}"), meta

    if any(k not in data for k in REQUIRED_KEYS):
        return _unknown(f"contract keys missing: {sorted(data)}"), meta

    copyright_text = str(data["copyright"]).strip()
    reasoning = str(data["reasoning"]).strip() or "no reasoning"
    if not copyright_text or copyright_text.upper() == "UNKNOWN":
        return (
            _unknown(reasoning if copyright_text.upper() == "UNKNOWN" else "empty copyright"),
            meta,
        )
    if _is_placeholder_copyright(copyright_text):
        return _unknown("placeholder template copyright"), meta
    return {"copyright": copyright_text, "reasoning": reasoning}, meta
