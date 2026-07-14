from __future__ import annotations

import json
import re
from pathlib import Path

from cost_tracking import CallMeta
from license_fetcher import LicenseFetchResult
from response_parser import VERDICT_SKIPPED, CopyrightResult, InputRow, QueryResult, VerificationResult


def make_slug(component_name: str) -> str:
    """Return a filesystem-safe identifier for a component_name value."""
    raw = component_name.strip()
    return re.sub(r'[\\/:*?"<>|]', "_", raw)


def _judgement_trailer(verification: VerificationResult) -> str:
    """Human-readable judge trace appended to the raw response file."""
    lines = [
        "",
        "=" * 60,
        "CONSISTENCY JUDGE (gpt-4.1-limitless)",
        "=" * 60,
        f"verdict:        {verification.verdict}",
        f"final_license:  {verification.final_license}",
        f"attempts:       {verification.judge_attempts}",
        f"elapsed_s:      {verification.judge_elapsed_s:.2f}",
        f"explanation:    {verification.judge_reasoning}",
    ]
    if verification.judge_raw:
        lines += ["", "judge raw response:", verification.judge_raw]
    return "\n".join(lines) + "\n"


def _fetch_trailer(fetch_result: LicenseFetchResult) -> str:
    lines = [
        "",
        "=" * 60,
        "LICENSE FILE FETCH",
        "=" * 60,
        f"source:         {fetch_result.source}",
        f"path:           {fetch_result.path}",
        f"ext:            {fetch_result.ext}",
        f"bytes_written:  {fetch_result.bytes_written}",
        f"content_type:   {fetch_result.content_type}",
        f"error:          {fetch_result.error}",
        f"original_url:   {fetch_result.original_url}",
        f"resolved_url:   {fetch_result.resolved_url}",
    ]
    return "\n".join(lines) + "\n"


def _eq_judge_trailer(label: str, query: str, raw_response: str) -> str:
    lines = [
        "",
        "=" * 60,
        f"EQUALITY JUDGE ({label})",
        "=" * 60,
        f"query:          {query}",
        f"raw_response:   {raw_response}",
    ]
    return "\n".join(lines) + "\n"


def _copyright_trailer(copyright_result: CopyrightResult) -> str:
    lines = [
        "",
        "=" * 60,
        "COPYRIGHT EXTRACTION (gpt-4.1)",
        "=" * 60,
        f"copyright:      {copyright_result.copyright}",
        f"reason:         {copyright_result.reason}",
        f"attempts:       {copyright_result.attempt_count}",
        f"elapsed_s:      {copyright_result.elapsed_s:.2f}",
    ]
    if copyright_result.raw_response:
        lines += ["", "copyright raw response:", copyright_result.raw_response]
    return "\n".join(lines) + "\n"


def save_response(
    responses_dir: Path,
    slug: str,
    raw: str,
    parsed: dict | None,
    verification: VerificationResult | None = None,
    fetch_result: LicenseFetchResult | None = None,
    inferencer_meta: "CallMeta | None" = None,
    eq_meta: "CallMeta | None" = None,
    cp_eq_meta: "CallMeta | None" = None,
    copyright_result: "CopyrightResult | None" = None,
    lic_eq_query: str = "",
    lic_eq_raw: str = "",
    cp_eq_query: str = "",
    cp_eq_raw: str = "",
) -> None:
    """Persist the raw text and (if available) parsed JSON for one response.

    When a consistency judge ran, its full trace is appended to the raw text
    file and embedded as a ``verification`` block in the parsed JSON file.
    """
    pkg_dir = responses_dir / slug
    pkg_dir.mkdir(parents=True, exist_ok=True)

    raw_text = raw
    if verification is not None and verification.verdict != VERDICT_SKIPPED:
        raw_text = raw + _judgement_trailer(verification)
    if fetch_result is not None:
        raw_text += _fetch_trailer(fetch_result)
    if copyright_result is not None:
        raw_text += _copyright_trailer(copyright_result)
    if lic_eq_query or lic_eq_raw:
        raw_text += _eq_judge_trailer("license", lic_eq_query, lic_eq_raw)
    if cp_eq_query or cp_eq_raw:
        raw_text += _eq_judge_trailer("copyright", cp_eq_query, cp_eq_raw)
    (pkg_dir / f"{slug}_raw.txt").write_text(raw_text, encoding="utf-8")

    if parsed is not None:
        payload = dict(parsed)
        if inferencer_meta is not None:
            payload["inferencer_call"] = inferencer_meta.json_block()
        if verification is not None:
            payload["verification"] = verification.json_block()
        if eq_meta is not None:
            lic_eq_block = eq_meta.json_block()
            if lic_eq_query:
                lic_eq_block["query"] = lic_eq_query
            if lic_eq_raw:
                lic_eq_block["raw_response"] = lic_eq_raw
            payload["license_eq_call"] = lic_eq_block
        if cp_eq_meta is not None:
            cp_eq_block = cp_eq_meta.json_block()
            if cp_eq_query:
                cp_eq_block["query"] = cp_eq_query
            if cp_eq_raw:
                cp_eq_block["raw_response"] = cp_eq_raw
            payload["copyright_eq_call"] = cp_eq_block
        if fetch_result is not None:
            payload["license_file"] = fetch_result.json_block()
        if copyright_result is not None:
            copyright_block: dict = {
                "copyright": copyright_result.copyright,
                "reason": copyright_result.reason,
                "attempts": copyright_result.attempt_count,
                "elapsed_s": round(copyright_result.elapsed_s, 3),
            }
            if copyright_result.extract_meta is not None:
                copyright_block["call"] = copyright_result.extract_meta.json_block()
            payload["copyright_extraction"] = copyright_block
        (pkg_dir / f"{slug}_json.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def progress_bar(done: int, total: int, width: int = 35) -> str:
    filled = int(width * done / total) if total else 0
    return f"[{'█' * filled}{'░' * (width - filled)}] {done}/{total}"


def format_status_suffix(
    row: InputRow,
    result: QueryResult,
    verification: VerificationResult | None = None,
) -> str:
    label = row.component_name.strip() or f"{row.lib_name.strip()}@{row.version.strip()}"
    status = result.predicted_license or "[no response]"
    if verification is not None and verification.final_license != result.predicted_license:
        # Judge overrode the prediction (e.g. inconsistent -> UNKNOWN).
        status = f"{status}->{verification.final_license}"
    suffix = f"{label} → {status}"
    return suffix if len(suffix) <= 60 else suffix[:57] + "..."


def build_output_row(
    row: InputRow,
    result: QueryResult,
    verification: VerificationResult | None = None,
    fetch_result: LicenseFetchResult | None = None,
    *,
    cache_hit: bool | None = None,
    outcome: str = "",
    lic_eq: str = "",
    eq_kind: str = "",
    lic_eq_raw: str = "",
    cp_eq: str = "",
    cp_eq_kind: str = "",
    cp_eq_raw: str = "",
    inferencer_meta: "CallMeta | None" = None,
    judge_meta: "CallMeta | None" = None,
    eq_meta: "CallMeta | None" = None,
    cp_eq_meta: "CallMeta | None" = None,
    copyright_result: "CopyrightResult | None" = None,
) -> dict:
    """Merge the original CSV row fields with the query and verification fields.

    ``outcome`` is the bucket from ``response_parser.classify_outcome`` and is
    emitted as its own column so the CSV is self-describing without having to
    cross-reference predicted_license, parse_error, and judge_verdict.
    """
    out = {"component_name": row.component_name, "purl": row.purl}
    out.update(row.extra)
    if cache_hit is not None:
        out["cache_hit"] = "yes" if cache_hit else "no"
    if outcome:
        out["outcome"] = outcome
    out.update(result.csv_fields())
    # results.csv uses stage-prefixed names for the inferencer's raw output and
    # wall time so each pipeline stage reads consistently. The underlying
    # ``csv_fields()`` keys stay unchanged because cache_store reuses them.
    if "raw_response" in out:
        out["inferencer_raw_response"] = out.pop("raw_response")
    if "elapsed_s" in out:
        out["inferencer_elapsed_s"] = out.pop("elapsed_s")
    if verification is not None:
        out.update(verification.csv_fields())
        if "judge_raw" in out:
            out["judge_raw_response"] = out.pop("judge_raw")
    if fetch_result is not None:
        out.update(fetch_result.csv_fields())
    if lic_eq:
        out["lic_eq"] = lic_eq
    if eq_kind:
        out["eq_kind"] = eq_kind
    out["license_eq_raw_response"] = lic_eq_raw
    if cp_eq:
        out["cp_eq"] = cp_eq
    if cp_eq_kind:
        out["cp_eq_kind"] = cp_eq_kind
    out["copyright_eq_raw_response"] = cp_eq_raw
    out["inferencer_cost_usd"] = (
        inferencer_meta.cost_csv() if inferencer_meta else ""
    )
    out["judge_cost_usd"] = judge_meta.cost_csv() if judge_meta else ""
    out["eq_cost_usd"] = eq_meta.cost_csv() if eq_meta else ""
    out["cp_eq_cost_usd"] = cp_eq_meta.cost_csv() if cp_eq_meta else ""
    out["copyright_produced"] = copyright_result.copyright if copyright_result else ""
    out["copyright_reason"] = copyright_result.reason if copyright_result else ""
    out["copyright_raw_response"] = copyright_result.raw_response if copyright_result else ""
    out["copyright_elapsed_s"] = f"{copyright_result.elapsed_s:.2f}" if copyright_result else ""
    out["copyright_attempts"] = str(copyright_result.attempt_count) if copyright_result else ""
    out["copyright_cost_usd"] = (
        copyright_result.extract_meta.cost_csv()
        if copyright_result and copyright_result.extract_meta
        else ""
    )
    # Summary group: per-row totals
    _elapsed_parts = [
        result.elapsed_s,
        verification.judge_elapsed_s if verification else 0.0,
        copyright_result.elapsed_s if copyright_result else 0.0,
        eq_meta.elapsed_s if eq_meta else 0.0,
        cp_eq_meta.elapsed_s if cp_eq_meta else 0.0,
    ]
    out["total_elapsed_s"] = f"{sum(_elapsed_parts):.2f}"
    _cost_parts = [
        inferencer_meta.cost_usd if inferencer_meta and inferencer_meta.cost_usd is not None else None,
        judge_meta.cost_usd if judge_meta and judge_meta.cost_usd is not None else None,
        eq_meta.cost_usd if eq_meta and eq_meta.cost_usd is not None else None,
        cp_eq_meta.cost_usd if cp_eq_meta and cp_eq_meta.cost_usd is not None else None,
        copyright_result.extract_meta.cost_usd
        if copyright_result and copyright_result.extract_meta and copyright_result.extract_meta.cost_usd is not None
        else None,
    ]
    _known_costs = [c for c in _cost_parts if c is not None]
    out["total_cost_usd"] = f"{sum(_known_costs):.6f}" if _known_costs else ""
    return out


def build_enriched_fieldnames(input_fieldnames: list[str]) -> list[str]:
    """Build enriched CSV fieldnames by keeping input order and appending missing special columns.
    
    Ensures 'license_name' and 'license_code_url' are present in the fieldnames.
    If they already exist, they are kept in their original positions.
    If they are absent, they are appended to the end.
    
    Args:
        input_fieldnames: The fieldnames from the input CSV.
        
    Returns:
        A list of fieldnames for the enriched CSV, with license_name and license_code_url
        guaranteed to be present.
    """
    fieldnames = list(input_fieldnames)
    for col in ("license_name", "license_code_url", "copyright"):
        if col not in fieldnames:
            fieldnames.append(col)
    return fieldnames


def build_enriched_row(
    raw_row: dict,
    final_license: str,
    license_url: str,
    copyright: str = "",
) -> dict:
    """Build an enriched CSV row by copying the original row and updating license fields.

    Creates a new row dict that is a copy of raw_row, with 'license_name',
    'license_code_url', and 'copyright' set to the provided values. This
    overwrites any pre-existing values in the raw row.

    Args:
        raw_row: The original input row as a dictionary.
        final_license: The trusted inferred license (e.g., 'MIT' or 'UNKNOWN' on failures).
        license_url: The inferred license URL as-is (e.g., 'https://...' or '' when none).
        copyright: The final copyright value (extracted, provided, or 'UNKNOWN').

    Returns:
        A new dict with the license and copyright fields updated.
    """
    out = dict(raw_row)
    out["license_name"] = final_license
    out["license_code_url"] = license_url
    out["copyright"] = copyright
    return out
