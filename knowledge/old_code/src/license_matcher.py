from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

import config
from cost_tracking import CallMeta

_NON_EQUALABLE = {"", "UNKNOWN", "N/A", "[PARSE ERROR]"}


@dataclass(frozen=True)
class LicenseMatchResult:
    equal: bool
    kind: str
    eq_meta: CallMeta | None = None

    def csv_fields(self) -> dict[str, str]:
        return {
            "lic_eq": "yes" if self.equal else "no",
            "eq_kind": self.kind,
        }


def _normalize_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _is_non_equalable(value: str) -> bool:
    return _normalize_key(value).upper() in _NON_EQUALABLE


def _canonicalize_alias(value: str) -> str:
    return config.LICENSE_ALIASES.get(_normalize_key(value), "")


async def compare_licenses(
    expected_license: str,
    actual_license: str,
    *,
    llm_judge: Callable[[str, str], Awaitable[tuple[bool, CallMeta | None]]] | None = None,
) -> LicenseMatchResult:
    expected = (expected_license or "").strip()
    actual = (actual_license or "").strip()

    if expected == actual and expected:
        return LicenseMatchResult(equal=True, kind="exact")

    if expected.lower() == actual.lower() and expected and actual:
        return LicenseMatchResult(equal=True, kind="lower")

    if _is_non_equalable(expected) or _is_non_equalable(actual):
        return LicenseMatchResult(equal=False, kind="not_equal")

    expected_alias = _canonicalize_alias(expected)
    actual_alias = _canonicalize_alias(actual)
    if expected_alias and actual_alias and expected_alias == actual_alias:
        return LicenseMatchResult(equal=True, kind="alias")

    if llm_judge is None:
        return LicenseMatchResult(equal=False, kind="not_equal")

    verdict, eq_meta = await llm_judge(expected, actual)
    if verdict:
        return LicenseMatchResult(equal=True, kind="llm", eq_meta=eq_meta)
    if eq_meta is None:
        return LicenseMatchResult(equal=False, kind="judge_unavailable")
    return LicenseMatchResult(equal=False, kind="not_equal", eq_meta=eq_meta)