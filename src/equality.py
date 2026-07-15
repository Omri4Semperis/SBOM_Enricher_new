"""Audit-mode equality ladders: name, copyright, URL content (ADR 0002)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from download import fetch_license_file
from gpt41_client import Gpt41Client
from pricing import CallMeta
from prompts import (
    equality_copyright_prompts,
    equality_name_prompts,
    equality_url_prompts,
)

_COPYRIGHT_MARK_RE = re.compile(r"\(c\)|©|ï¿½?|copyright", re.IGNORECASE)
_ALL_RIGHTS_RE = re.compile(r"all rights reserved\.?", re.IGNORECASE)
_TRAILING_PUNCT_RE = re.compile(r"[\s.,;:]+$")


@dataclass(frozen=True)
class EqResult:
    verdict: str  # TRUE | FALSE
    reason: str
    meta: CallMeta = field(default_factory=CallMeta)


def _normalize_name(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("©", "(c)").replace("ï¿½", "(c)").replace("ï¿", "(c)")
    return " ".join(text.split())


def _normalize_copyright(value: str) -> str:
    text = (value or "").strip()
    text = _COPYRIGHT_MARK_RE.sub(" ", text)
    text = _ALL_RIGHTS_RE.sub(" ", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    return " ".join(text.lower().split())


def _normalize_license_bytes(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(text.lower().split())
    return text


async def _judge(
    client: Gpt41Client,
    system: str,
    user: str,
) -> EqResult:
    data, meta = await client.complete_json(system, user)
    verdict = str(data.get("verdict", "")).strip().upper()
    reasoning = str(data.get("reasoning", "")).strip() or "judge"
    if verdict not in ("TRUE", "FALSE"):
        return EqResult("FALSE", f"judge_bad_verdict:{verdict or 'empty'}", meta=meta)
    return EqResult(verdict, f"judge:{reasoning}", meta=meta)


async def _text_ladder(
    left: str,
    right: str,
    *,
    normalize,
    prompts_fn,
    client: Gpt41Client | None,
) -> EqResult:
    a = (left or "").strip()
    b = (right or "").strip()
    if a == b:
        return EqResult("TRUE", "identical")
    if normalize(a) == normalize(b) and normalize(a):
        return EqResult("TRUE", "normalized")
    if client is None:
        return EqResult("FALSE", "no_judge")
    system, user = prompts_fn(a, b)
    return await _judge(client, system, user)


async def compare_name(
    inferred: str,
    ground_truth: str,
    *,
    client: Gpt41Client | None = None,
) -> EqResult:
    return await _text_ladder(
        inferred,
        ground_truth,
        normalize=_normalize_name,
        prompts_fn=equality_name_prompts,
        client=client,
    )


async def compare_copyright(
    inferred: str,
    ground_truth: str,
    *,
    client: Gpt41Client | None = None,
) -> EqResult:
    return await _text_ladder(
        inferred,
        ground_truth,
        normalize=_normalize_copyright,
        prompts_fn=equality_copyright_prompts,
        client=client,
    )


async def compare_url_content(
    inferred_url: str,
    gt_url: str,
    dest_dir: Path,
    slug: str,
    *,
    client: Gpt41Client | None = None,
) -> EqResult:
    """Download both URLs; compare LICENSE bytes (ADR 0002). Empty purl → no npm fallback."""
    inf = await fetch_license_file((inferred_url or "").strip(), "", dest_dir, f"{slug}__eq_inf")
    if not inf.ok:
        return EqResult("FALSE", "inferred_url_download_failed")
    gt = await fetch_license_file((gt_url or "").strip(), "", dest_dir, f"{slug}__eq_gt")
    if not gt.ok:
        return EqResult("FALSE", "gt_url_download_failed")

    a = inf.saved_path.read_bytes()
    b = gt.saved_path.read_bytes()
    if a == b:
        return EqResult("TRUE", "identical")
    if _normalize_license_bytes(a) == _normalize_license_bytes(b):
        return EqResult("TRUE", "normalized")
    if client is None:
        return EqResult("FALSE", "no_judge")
    system, user = equality_url_prompts(
        a.decode("utf-8", errors="replace"),
        b.decode("utf-8", errors="replace"),
    )
    return await _judge(client, system, user)
