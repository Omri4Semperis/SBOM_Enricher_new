from __future__ import annotations

import json
from dataclasses import dataclass, field

from cost_tracking import CallMeta


def is_value_missing(value: "str | None") -> bool:
    """Return True when a CSV cell value is absent, empty, or whitespace-only."""
    if value is None:
        return True
    return not str(value).strip()


@dataclass
class InputRow:
    component_name: str
    lib_name: str
    version: str
    purl: str
    extra: dict = field(default_factory=dict)

    @staticmethod
    def _split_component_name(component_name: str) -> tuple[str, str, str]:
        """Return ``(clean_component_name, lib_name, version)``.

        Rules:
        - Trim whitespace.
        - Strip leading/trailing '@'.
        - Use only the last remaining '@' as the lib/version separator.
        """
        clean = component_name.strip().strip("@")
        lib_name, has_sep, version = clean.rpartition("@")
        if not has_sep:
            lib_name = clean
            version = ""
        return clean, lib_name.strip(), version.strip()

    @classmethod
    def from_csv_row(cls, row: dict) -> "InputRow":
        component_name, lib_name, version = cls._split_component_name(
            str(row["component_name"])
        )
        return cls(
            component_name=component_name,
            lib_name=lib_name,
            version=version,
            purl=row.get("purl", ""),
            extra={k: v for k, v in row.items() if k not in {"component_name", "purl"}},
        )


@dataclass
class QueryResult:
    predicted_license: str
    license_url: str
    reasoning: str
    raw_response: str
    elapsed_s: float
    parse_error: bool = False
    inferencer_meta: "CallMeta | None" = None

    def csv_fields(self) -> dict:
        return {
            "predicted_license": self.predicted_license,
            "license_url": self.license_url,
            "reasoning": self.reasoning,
            "raw_response": self.raw_response,
            "elapsed_s": f"{self.elapsed_s:.2f}",
        }


@dataclass(frozen=True)
class RowPlan:
    """Pure per-row execution plan derived from input-value presence."""

    need_license: bool
    need_url: bool
    need_copyright: bool
    need_inference: bool
    need_download: bool
    should_judge_license: bool


def build_row_plan(
    row: "InputRow",
    *,
    force_license_inference: bool = False,
    force_copyright_extraction: bool = False,
) -> RowPlan:
    """Return row-level operation flags from the Phase-3 decision matrix.

    Missing columns are treated the same as blank values.
    """
    license_missing = is_value_missing(row.extra.get("license_name", ""))
    url_missing = is_value_missing(row.extra.get("license_code_url", ""))
    copyright_missing = is_value_missing(row.extra.get("copyright", ""))

    need_license = license_missing or force_license_inference
    need_url = url_missing
    need_copyright = copyright_missing or force_copyright_extraction

    return RowPlan(
        need_license=need_license,
        need_url=need_url,
        need_copyright=need_copyright,
        need_inference=(need_license or need_url),
        need_download=(need_url or need_copyright),
        should_judge_license=license_missing,
    )


@dataclass
class CopyrightResult:
    """Result of the copyright extraction step for one row.

    ``reason`` is one of the ``COPYRIGHT_REASON_*`` constants from ``config``.
    When extraction succeeds, ``copyright`` holds the extracted text and
    ``reason`` is ``COPYRIGHT_REASON_EXTRACTED``.  When it fails, ``copyright``
    is ``COPYRIGHT_UNKNOWN`` and ``reason`` explains why.
    """

    copyright: str
    reason: str
    raw_response: str
    elapsed_s: float
    attempt_count: int = 0
    extract_meta: "CallMeta | None" = None


# Verdict values produced by the consistency judge.
VERDICT_CONSISTENT = "CONSISTENT"
VERDICT_INCONSISTENT = "INCONSISTENT"
VERDICT_ERROR = "ERROR"  # judge could not return a parsable verdict after retries
VERDICT_SKIPPED = "SKIPPED"  # nothing meaningful to judge (empty/parse error/UNKNOWN)

# ---------------------------------------------------------------------------
# Per-row outcome classification
# ---------------------------------------------------------------------------
# Each processed row is bucketed into exactly one of these categories by
# ``classify_outcome``. The CSV gets the value as an ``outcome`` column and
# ``run_info.json`` exposes counts per category, so users can see *why* a row
# ended up UNKNOWN (inferencer said so vs. inferencer broke vs. judge broke
# vs. judge contradicted) without having to re-derive it from the other
# columns.
OUTCOME_OK = "ok"
OUTCOME_INFERENCER_NO_RESPONSE = "inferencer_no_response"
OUTCOME_INFERENCER_PARSE_ERROR = "inferencer_parse_error"
OUTCOME_INFERENCER_UNKNOWN = "inferencer_unknown"
OUTCOME_JUDGE_ERROR = "judge_error"
OUTCOME_JUDGE_INCONSISTENT = "judge_inconsistent"

ALL_OUTCOMES: tuple[str, ...] = (
    OUTCOME_OK,
    OUTCOME_INFERENCER_UNKNOWN,
    OUTCOME_INFERENCER_NO_RESPONSE,
    OUTCOME_INFERENCER_PARSE_ERROR,
    OUTCOME_JUDGE_ERROR,
    OUTCOME_JUDGE_INCONSISTENT,
)

# Outcomes that count as "the system failed" rather than "we successfully
# concluded that the license is unknown / inconsistent".
FAILURE_OUTCOMES: frozenset[str] = frozenset({
    OUTCOME_INFERENCER_NO_RESPONSE,
    OUTCOME_INFERENCER_PARSE_ERROR,
    OUTCOME_JUDGE_ERROR,
})


@dataclass
class VerificationResult:
    """Outcome of the gpt-4.1 consistency check for one inference.

    ``final_license`` is the license to trust after verification: the original
    prediction when CONSISTENT or SKIPPED, otherwise ``UNKNOWN``.
    """

    verdict: str
    consistent: bool | None
    judge_reasoning: str
    judge_raw: str
    judge_elapsed_s: float
    judge_attempts: int
    final_license: str
    judge_meta: "CallMeta | None" = None

    @classmethod
    def skipped(cls, predicted_license: str) -> "VerificationResult":
        return cls(
            verdict=VERDICT_SKIPPED,
            consistent=None,
            judge_reasoning="",
            judge_raw="",
            judge_elapsed_s=0.0,
            judge_attempts=0,
            final_license=predicted_license,
        )

    def csv_fields(self) -> dict:
        consistent = "" if self.consistent is None else ("yes" if self.consistent else "no")
        return {
            "final_license": self.final_license,
            "judge_verdict": self.verdict,
            "judge_consistent": consistent,
            "judge_reasoning": self.judge_reasoning,
            "judge_raw": self.judge_raw,
            "judge_attempts": str(self.judge_attempts),
            "judge_elapsed_s": f"{self.judge_elapsed_s:.2f}",
        }

    def json_block(self) -> dict:
        block = {
            "verdict": self.verdict,
            "consistent": self.consistent,
            "explanation": self.judge_reasoning,
            "attempts": self.judge_attempts,
            "elapsed_s": round(self.judge_elapsed_s, 2),
            "final_license": self.final_license,
            "raw": self.judge_raw,
        }
        if self.judge_meta is not None:
            block["call"] = self.judge_meta.json_block()
        return block


def parse_judge_response(raw: str) -> tuple[str, str]:
    """Parse a judge response into ``(verdict, explanation)``.

    Raises ``ValueError`` if the response is not valid JSON or does not contain
    a recognized verdict, so the caller can retry.
    """
    snippet = extract_json(raw)
    if not snippet:
        raise ValueError("no JSON object found in judge response")
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in judge response: {exc}") from exc

    verdict = str(data.get("verdict", "")).strip().upper()
    if verdict not in (VERDICT_CONSISTENT, VERDICT_INCONSISTENT):
        raise ValueError(f"unrecognized verdict: {verdict!r}")
    explanation = str(data.get("explanation", "")).strip()
    return verdict, explanation


def extract_json(raw: str) -> str:
    """Extract the first complete JSON object from a string."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return raw[start : end + 1]


def classify_outcome(result: "QueryResult", verification: "VerificationResult") -> str:
    """Bucket one processed row into a single outcome category.

    Order matters: an empty raw response wins over a parse error, which wins
    over an UNKNOWN/empty predicted license. Only when the inferencer side is
    fully clean do judge-side outcomes (``ERROR`` / ``INCONSISTENT``) apply.
    A SKIPPED judge with a concrete predicted license is still ``ok``: the
    inferencer succeeded and the judge had nothing meaningful to challenge.
    """
    if not result.raw_response:
        return OUTCOME_INFERENCER_NO_RESPONSE
    if result.parse_error:
        return OUTCOME_INFERENCER_PARSE_ERROR
    if (result.predicted_license or "").strip().upper() in {"", "UNKNOWN"}:
        return OUTCOME_INFERENCER_UNKNOWN
    if verification.verdict == VERDICT_ERROR:
        return OUTCOME_JUDGE_ERROR
    if verification.verdict == VERDICT_INCONSISTENT:
        return OUTCOME_JUDGE_INCONSISTENT
    return OUTCOME_OK


def parse_response(raw: str, elapsed: float) -> QueryResult:
    """Parse a Claude response string into a QueryResult.

    On JSON parse failure, sets predicted_license to '[parse error]' and
    stores the first 500 chars of raw output as reasoning.
    """
    if not raw:
        return QueryResult(
            predicted_license="",
            license_url="",
            reasoning="",
            raw_response=raw,
            elapsed_s=elapsed,
        )

    try:
        data = json.loads(extract_json(raw))
        return QueryResult(
            predicted_license=data.get("license", ""),
            license_url=data.get("license_url", ""),
            reasoning=data.get("reasoning", ""),
            raw_response=raw,
            elapsed_s=elapsed,
        )
    except json.JSONDecodeError:
        return QueryResult(
            predicted_license="[parse error]",
            license_url="",
            reasoning=raw[:500],
            raw_response=raw,
            elapsed_s=elapsed,
            parse_error=True,
        )
