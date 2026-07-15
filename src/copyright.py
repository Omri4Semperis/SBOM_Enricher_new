"""Copyright resolution: LICENSE file → npm author → Claude web → UNKNOWN."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import unquote

import requests
from claude_client import infer_copyright_web
from gpt41_client import Gpt41Client
from pricing import CallMeta, combine
from prompts import copyright_prompt

REQUIRED_KEYS = ("copyright", "reasoning")
_NPM_REGISTRY = "https://registry.npmjs.org"
_FETCH_TIMEOUT_S = 15.0

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


def _npm_package_name(purl: str) -> str | None:
    """Name-only extract from pkg:npm/... purl; None if not npm."""
    cleaned = (purl or "").strip()
    if not cleaned.lower().startswith("pkg:npm/"):
        return None
    remainder = cleaned[len("pkg:npm/") :]
    remainder = remainder.split("?", 1)[0].split("#", 1)[0]
    if "@" not in remainder:
        return None
    name_part, _, _version = remainder.rpartition("@")
    package_name = unquote(name_part).strip()
    return package_name or None


def _author_name_from_registry(metadata: dict) -> str | None:
    """author.name or string author only; never contributors/maintainers."""
    author = metadata.get("author")
    if isinstance(author, dict):
        name = str(author.get("name", "")).strip()
        return name or None
    if isinstance(author, str):
        name = author.split("<", 1)[0].split("(", 1)[0].strip()
        return name or None
    return None


def _npm_author_copyright(purl: str) -> str | None:
    """Return 'Copyright (c) {name}' from npm registry author, or None."""
    package_name = _npm_package_name(purl)
    if not package_name:
        return None
    cleaned = purl.strip()
    remainder = cleaned[len("pkg:npm/") :].split("?", 1)[0].split("#", 1)[0]
    _name_part, _, version = remainder.rpartition("@")
    version = version.strip()

    urls = []
    if version:
        urls.append(f"{_NPM_REGISTRY}/{package_name}/{version}")
    urls.append(f"{_NPM_REGISTRY}/{package_name}/latest")

    for url in urls:
        try:
            resp = requests.get(url, timeout=_FETCH_TIMEOUT_S)
        except requests.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            metadata = resp.json()
        except ValueError:
            continue
        if not isinstance(metadata, dict):
            continue
        name = _author_name_from_registry(metadata)
        if name and not _is_placeholder_copyright(name):
            return f"Copyright (c) {name}"
    return None


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


async def resolve_copyright(
    license_text: str,
    purl: str,
    lib_name: str,
    version: str,
    model: str,
) -> tuple[dict, CallMeta]:
    """File → npm author → Claude web → UNKNOWN. Never overwrite an earlier success."""
    file_data, file_meta = await extract_copyright(license_text)
    if file_data["copyright"].upper() != "UNKNOWN":
        return file_data, file_meta

    npm = await asyncio.to_thread(_npm_author_copyright, purl or "")
    if npm:
        return {"copyright": npm, "reasoning": "npm_author"}, file_meta

    web_data, web_meta = await infer_copyright_web(purl, lib_name, version, model)
    meta = combine([file_meta, web_meta])
    copyright_text = str(web_data.get("copyright", "")).strip()
    reasoning = str(web_data.get("reasoning", "")).strip() or "no reasoning"
    if (
        not copyright_text
        or copyright_text.upper() == "UNKNOWN"
        or _is_placeholder_copyright(copyright_text)
    ):
        reason = (
            "placeholder template copyright"
            if copyright_text and _is_placeholder_copyright(copyright_text)
            else reasoning if copyright_text.upper() == "UNKNOWN" else "web copyright UNKNOWN"
        )
        return _unknown(reason), meta
    return {"copyright": copyright_text, "reasoning": f"web: {reasoning}"}, meta
