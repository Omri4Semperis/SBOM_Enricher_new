from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

import config
from cost_tracking import CallMeta
from license_fetcher import FETCH_SOURCE_DOWNLOADED, LicenseFetchResult, license_filename
from output import make_slug
from response_parser import OUTCOME_OK, CopyrightResult, InputRow, QueryResult, VerificationResult, classify_outcome


CACHE_FIELDNAMES = [
    "lib_name",
    "version",
    "component_name",
    "purl",
    "run_id",
    "outcome",
    "predicted_license",
    "final_license",
    "judge_verdict",
    "judge_consistent",
    "judge_reasoning",
    "judge_raw",
    "judge_attempts",
    "judge_elapsed_s",
    "license_url",
    "reasoning",
    "raw_response",
    "elapsed_s",
    "license_file_source",
    "license_file_path",
    "license_file_ext",
    "license_file_error",
    "license_file_original_url",
    "license_file_resolved_url",
    "license_file_content_type",
    "license_file_bytes",
    "inferencer_cost_usd",
    "judge_cost_usd",
    "copyright",
    "copyright_reason",
    "copyright_raw_response",
    "copyright_elapsed_s",
    "copyright_attempts",
    "copyright_cost_usd",
]


@dataclass(frozen=True)
class CacheEntry:
    row: InputRow
    run_id: str
    outcome: str
    result: QueryResult
    verification: VerificationResult
    fetch_result: LicenseFetchResult
    copyright_result: CopyrightResult | None = None
    copyright_cost_usd: float | None = None

    def csv_row(self) -> dict[str, str]:
        payload = {
            "lib_name": self.row.lib_name,
            "version": self.row.version,
            "component_name": self.row.component_name,
            "purl": self.row.purl,
            "run_id": self.run_id,
            "outcome": self.outcome,
        }
        payload.update(self.result.csv_fields())
        payload.update(self.verification.csv_fields())
        payload.update(self.fetch_result.cache_fields())

        # Persist cost metadata
        payload["inferencer_cost_usd"] = (
            self.result.inferencer_meta.cost_csv() if self.result.inferencer_meta else ""
        )
        payload["judge_cost_usd"] = (
            self.verification.judge_meta.cost_csv() if self.verification.judge_meta else ""
        )

        # Persist copyright data
        cr = self.copyright_result
        if cr is not None:
            payload["copyright"] = cr.copyright
            payload["copyright_reason"] = cr.reason
            payload["copyright_raw_response"] = cr.raw_response
            payload["copyright_elapsed_s"] = f"{cr.elapsed_s:.2f}"
            payload["copyright_attempts"] = str(cr.attempt_count)
            if cr.extract_meta is not None:
                payload["copyright_cost_usd"] = cr.extract_meta.cost_csv()
            elif self.copyright_cost_usd is not None:
                payload["copyright_cost_usd"] = f"{self.copyright_cost_usd:.6f}"
            else:
                payload["copyright_cost_usd"] = ""
        else:
            payload["copyright"] = ""
            payload["copyright_reason"] = ""
            payload["copyright_raw_response"] = ""
            payload["copyright_elapsed_s"] = ""
            payload["copyright_attempts"] = "0"
            payload["copyright_cost_usd"] = ""

        return payload


def cache_csv_path(cache_dir: Path) -> Path:
    return cache_dir / "cache.csv"


def _cache_license_relpath(component_name: str, ext: str) -> str:
    slug = make_slug(component_name)
    return (Path("files") / slug / license_filename(slug, ext)).as_posix()


def _cache_license_abspath(cache_dir: Path, component_name: str, ext: str) -> Path:
    return cache_dir / Path(_cache_license_relpath(component_name, ext))


def cache_key(lib_name: str, version: str, purl: str) -> tuple[str, str, str]:
    return lib_name, version, purl


def cache_key_for_row(row: InputRow) -> tuple[str, str, str]:
    return cache_key(row.lib_name, row.version, row.purl)


def make_cache_entry(
    row: InputRow,
    result: QueryResult,
    verification: VerificationResult,
    fetch_result: LicenseFetchResult,
    *,
    run_id: str,
    outcome: str | None = None,
    copyright_result: CopyrightResult | None = None,
) -> CacheEntry:
    return CacheEntry(
        row=row,
        run_id=run_id,
        outcome=outcome or classify_outcome(result, verification),
        result=result,
        verification=verification,
        fetch_result=fetch_result,
        copyright_result=copyright_result,
        copyright_cost_usd=(
            copyright_result.extract_meta.cost_usd
            if copyright_result is not None and copyright_result.extract_meta is not None
            else None
        ),
    )


def is_file_cached(cache_dir: Path, entry: CacheEntry) -> bool:
    if entry.fetch_result.source != FETCH_SOURCE_DOWNLOADED:
        return False
    if not entry.fetch_result.path:
        return False
    return (cache_dir / entry.fetch_result.path).exists()


def load_cache(cache_dir: Path, *, model: str) -> dict[tuple[str, str, str], CacheEntry]:
    csv_path = cache_csv_path(cache_dir)
    if not csv_path.exists():
        return {}

    def _cost(value: str) -> float | None:
        value = (value or "").strip()
        return float(value) if value else None

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    entries: dict[tuple[str, str, str], CacheEntry] = {}
    for raw in rows:
        row = InputRow(
            component_name=raw.get("component_name", ""),
            lib_name=raw.get("lib_name", ""),
            version=raw.get("version", ""),
            purl=raw.get("purl", ""),
            extra={},
        )
        result = QueryResult(
            predicted_license=raw.get("predicted_license", ""),
            license_url=raw.get("license_url", ""),
            reasoning=raw.get("reasoning", ""),
            raw_response=raw.get("raw_response", ""),
            elapsed_s=float(raw.get("elapsed_s", "0") or 0.0),
            parse_error=(raw.get("predicted_license", "").strip() == "[parse error]"),
            inferencer_meta=CallMeta(
                model=model,
                cost_usd=_cost(raw.get("inferencer_cost_usd", "")),
                elapsed_s=float(raw.get("elapsed_s", "0") or 0.0),
            ),
        )
        consistent_raw = raw.get("judge_consistent", "").strip().lower()
        if consistent_raw == "yes":
            consistent = True
        elif consistent_raw == "no":
            consistent = False
        else:
            consistent = None
        verification = VerificationResult(
            verdict=raw.get("judge_verdict", ""),
            consistent=consistent,
            judge_reasoning=raw.get("judge_reasoning", ""),
            judge_raw=raw.get("judge_raw", ""),
            judge_elapsed_s=float(raw.get("judge_elapsed_s", "0") or 0.0),
            judge_attempts=int(raw.get("judge_attempts", "0") or 0),
            final_license=raw.get("final_license", ""),
            judge_meta=CallMeta(
                model=config.GPT41_MODEL,
                cost_usd=_cost(raw.get("judge_cost_usd", "")),
                elapsed_s=float(raw.get("judge_elapsed_s", "0") or 0.0),
            ),
        )
        fetch_result = LicenseFetchResult(
            source=raw.get("license_file_source", "") or "missing",
            path=raw.get("license_file_path", ""),
            ext=raw.get("license_file_ext", ""),
            error=raw.get("license_file_error", "") or "cache_entry_has_no_license_file",
            content_type=raw.get("license_file_content_type", ""),
            bytes_written=int(raw.get("license_file_bytes", "0") or 0),
            original_url=raw.get("license_file_original_url", ""),
            resolved_url=raw.get("license_file_resolved_url", ""),
        )
        # Reconstruct copyright result when present in stored row.
        # Old cache files lack these columns; treat missing/empty as None (no
        # copyright result stored).  extract_meta is intentionally left as None
        # so that cache-hit rows do not accumulate copyright extraction costs.
        copyright_value = raw.get("copyright", "").strip()
        if copyright_value:
            copyright_result: CopyrightResult | None = CopyrightResult(
                copyright=copyright_value,
                reason=raw.get("copyright_reason", ""),
                raw_response=raw.get("copyright_raw_response", ""),
                elapsed_s=float(raw.get("copyright_elapsed_s", "0") or 0.0),
                attempt_count=int(raw.get("copyright_attempts", "0") or 0),
                extract_meta=None,
            )
        else:
            copyright_result = None
        copyright_cost_usd = _cost(raw.get("copyright_cost_usd", ""))
        entry = CacheEntry(
            row=row,
            run_id=raw.get("run_id", ""),
            outcome=raw.get("outcome", "") or classify_outcome(result, verification),
            result=result,
            verification=verification,
            fetch_result=fetch_result,
            copyright_result=copyright_result,
            copyright_cost_usd=copyright_cost_usd,
        )
        if entry.outcome != OUTCOME_OK:
            continue
        entries[cache_key_for_row(row)] = entry
    return entries


def restore_cached_file(
    cache_dir: Path,
    out_dir: Path,
    component_name: str,
    fetch_result: LicenseFetchResult,
) -> LicenseFetchResult:
    if fetch_result.source != FETCH_SOURCE_DOWNLOADED or not fetch_result.ext:
        return fetch_result

    source = cache_dir / fetch_result.path if fetch_result.path else _cache_license_abspath(
        cache_dir,
        component_name,
        fetch_result.ext,
    )
    if not source.exists():
        return LicenseFetchResult.missing(
            "cached_file_missing",
            content_type=fetch_result.content_type,
            ext=fetch_result.ext,
            original_url=fetch_result.original_url,
        )

    slug = make_slug(component_name)
    rel_path = Path("licenses") / license_filename(slug, fetch_result.ext)
    target = out_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return LicenseFetchResult(
        source=FETCH_SOURCE_DOWNLOADED,
        path=rel_path.as_posix(),
        ext=fetch_result.ext,
        error="",
        content_type=fetch_result.content_type,
        bytes_written=fetch_result.bytes_written or source.stat().st_size,
        original_url=fetch_result.original_url,
        resolved_url=fetch_result.resolved_url,
    )


def write_cache(
    cache_dir: Path,
    entries: dict[tuple[str, str, str], CacheEntry],
    *,
    run_root: Path | None = None,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cache_csv_path(cache_dir)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_FIELDNAMES)
        writer.writeheader()
        for key in sorted(entries):
            entry = entries[key]
            row = entry.csv_row()
            if entry.fetch_result.source == FETCH_SOURCE_DOWNLOADED and entry.fetch_result.ext:
                target = _cache_license_abspath(cache_dir, entry.row.component_name, entry.fetch_result.ext)
                source = None
                if entry.fetch_result.path:
                    if run_root is not None:
                        candidate = run_root / Path(entry.fetch_result.path)
                        if candidate.exists():
                            source = candidate
                    if source is None:
                        candidate = cache_dir / Path(entry.fetch_result.path)
                        if candidate.exists():
                            source = candidate
                if source is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if source.resolve() != target.resolve():
                        shutil.copy2(source, target)
                row["license_file_path"] = _cache_license_relpath(
                    entry.row.component_name,
                    entry.fetch_result.ext,
                )
            writer.writerow(row)