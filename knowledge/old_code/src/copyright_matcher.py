from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable

import config
from cost_tracking import CallMeta

_NON_EQUALABLE = {"", "UNKNOWN", "N/A", "[PARSE ERROR]"}

# Symbols/words that mark a copyright notice but carry no comparison meaning:
# "(c)", "(C)", "©", and the literal word "copyright" all mean the same thing,
# and a trailing "all rights reserved" is boilerplate.
_COPYRIGHT_SYMBOL_RE = re.compile(r"\(c\)|©|copyright", re.IGNORECASE)
_ALL_RIGHTS_RESERVED_RE = re.compile(r"all rights reserved\.?", re.IGNORECASE)
_TRAILING_PUNCT_RE = re.compile(r"[\s.,;:]+$")


@dataclass(frozen=True)
class CopyrightMatchResult:
    equal: bool
    kind: str
    eq_meta: CallMeta | None = None

    def csv_fields(self) -> dict[str, str]:
        return {
            "cp_eq": "yes" if self.equal else "no",
            "cp_eq_kind": self.kind,
        }


def _is_non_equalable(value: str) -> bool:
    return " ".join((value or "").strip().split()).upper() in _NON_EQUALABLE


def _normalize_copyright(value: str) -> str:
    """Collapse formatting-only differences in a copyright notice.

    Strips the "copyright"/"(c)"/"©" markers and a trailing "all rights
    reserved", lowercases, collapses whitespace, and trims trailing
    punctuation — so notices that differ only in wording/symbols/case compare
    equal without invoking the LLM judge.
    """
    text = (value or "").strip()
    text = _COPYRIGHT_SYMBOL_RE.sub(" ", text)
    text = _ALL_RIGHTS_RESERVED_RE.sub(" ", text)
    text = _TRAILING_PUNCT_RE.sub("", text)
    text = " ".join(text.lower().split())
    return text


async def compare_copyrights(
    expected_copyright: str,
    actual_copyright: str,
    *,
    llm_judge: Callable[[str, str], Awaitable[tuple[bool, CallMeta | None]]] | None = None,
) -> CopyrightMatchResult:
    expected = (expected_copyright or "").strip()
    actual = (actual_copyright or "").strip()

    if expected == actual and expected:
        return CopyrightMatchResult(equal=True, kind="exact")

    if _is_non_equalable(expected) or _is_non_equalable(actual):
        return CopyrightMatchResult(equal=False, kind="not_equal")

    normalized_expected = _normalize_copyright(expected)
    normalized_actual = _normalize_copyright(actual)
    if normalized_expected and normalized_expected == normalized_actual:
        return CopyrightMatchResult(equal=True, kind="normalized")

    if llm_judge is None:
        return CopyrightMatchResult(equal=False, kind="not_equal")

    verdict, eq_meta = await llm_judge(expected, actual)
    if verdict:
        return CopyrightMatchResult(equal=True, kind="llm", eq_meta=eq_meta)
    if eq_meta is None:
        return CopyrightMatchResult(equal=False, kind="judge_unavailable")
    return CopyrightMatchResult(equal=False, kind="not_equal", eq_meta=eq_meta)
