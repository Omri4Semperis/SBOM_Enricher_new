from __future__ import annotations

import asyncio
import csv
import json
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from azure.identity import DefaultAzureCredential

import cli
import cache_store
import client
import config
import copyright_extractor
import copyright_matcher
import license_fetcher
import license_matcher
from equality_judge import EqualityJudgeClient
import output
import paths
import response_parser
import run_config
import verifier
from gpt41_client import Gpt41Client
from cost_tracking import CallMeta


# Per-operation debug log written to <out_dir>/debug.log. Each record is flushed
# on emit (logging flushes per record), so if the run hangs the log still shows
# exactly which call is in flight -- the last "start" with no matching "done"
# marks the stuck operation.
_debug_log = logging.getLogger("sbom_enricher")


def _setup_debug_log(out_dir: Path) -> None:
    """Attach a fresh file handler writing per-operation logs to <out_dir>/debug.log.

    Handlers are reset each run so repeated runs (e.g. tests) neither accumulate
    handlers nor duplicate lines, and the previous run's file is released.
    """
    for handler in list(_debug_log.handlers):
        _debug_log.removeHandler(handler)
        handler.close()
    file_handler = logging.FileHandler(out_dir / "debug.log", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    )
    _debug_log.addHandler(file_handler)
    _debug_log.setLevel(logging.INFO)
    _debug_log.propagate = False


def _ensure_azure_auth_ready() -> None:
    """Fail fast with one concise message when Azure auth is unavailable.

    The run requires Azure authentication for both the consistency judge and the
    license-equality judge. Checking once at startup avoids wasting live Claude
    calls and suppresses the Azure SDK's verbose credential-chain dump.
    """
    logging.getLogger("azure.identity").setLevel(logging.CRITICAL)

    credential = DefaultAzureCredential()
    try:
        credential.get_token(config.AZURE_TOKEN_SCOPE)
    except Exception as exc:
        summary = str(exc).splitlines()[0].strip() or type(exc).__name__
        raise SystemExit(
            "Azure authentication is required for the consistency judge and "
            "license-equality judge. Run `az login` or configure "
            f"DefaultAzureCredential, then rerun.\nDetails: {summary}"
        ) from None
    finally:
        close = getattr(credential, "close", None)
        if callable(close):
            close()


def _force_utf8_streams() -> None:
    """Ensure stdout/stderr can emit the progress-bar Unicode glyphs.

    When output is redirected or piped on Windows, the stream encoding defaults
    to the locale code page (e.g. cp1252), which cannot encode characters like
    'block' or the arrow used in progress output and would raise
    UnicodeEncodeError. Reconfigure to UTF-8 with a safe fallback.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


RESULT_EXTRA_FIELDS = [
    "cache_hit",
    "outcome",
    # --- inferencer (Claude): raw output first, then its interpretation ---
    "inferencer_raw_response",
    "predicted_license",
    "license_url",
    "reasoning",
    "inferencer_elapsed_s",
    "inferencer_cost_usd",
    # --- consistency judge (gpt-4.1): raw output first, then its verdict ---
    "judge_raw_response",
    "judge_verdict",
    "judge_consistent",
    "judge_reasoning",
    "final_license",
    "judge_attempts",
    "judge_elapsed_s",
    "judge_cost_usd",
    # --- license file fetch ---
    "license_file_source",
    "license_file_path",
    "license_file_ext",
    "license_file_error",
    "license_file_original_url",
    "license_file_resolved_url",
    # --- copyright extraction (gpt-4.1): raw output first, then its result ---
    "copyright_raw_response",
    "copyright_produced",
    "copyright_reason",
    "copyright_attempts",
    "copyright_elapsed_s",
    "copyright_cost_usd",
    # --- license equality (accuracy scoring): raw judge output first ---
    "license_eq_raw_response",
    "lic_eq",
    "eq_kind",
    "eq_cost_usd",
    # --- copyright equality (accuracy scoring): raw judge output first ---
    "copyright_eq_raw_response",
    "cp_eq",
    "cp_eq_kind",
    "cp_eq_cost_usd",
    # --- summary ---
    "total_elapsed_s",
    "total_cost_usd",
]


DEFAULT_RUN_CONFIG_PATH = paths.PROJECT_ROOT / "run_configs" / "default_config.json"


def build_row_plan(
    row: response_parser.InputRow,
    *,
    force_license_inference: bool,
    force_copyright_extraction: bool = False,
) -> response_parser.RowPlan:
    """Build a pure per-row plan from current input fields."""
    return response_parser.build_row_plan(
        row,
        force_license_inference=force_license_inference,
        force_copyright_extraction=force_copyright_extraction,
    )


@dataclass
class ProcessedRow:
    raw_response: str
    row_plan: response_parser.RowPlan
    query_result: response_parser.QueryResult
    verification: response_parser.VerificationResult
    fetch_result: license_fetcher.LicenseFetchResult
    resolved_license_name: str
    resolved_license_url: str
    inferred_license_for_accuracy: str
    copyright_result: response_parser.CopyrightResult | None = None
    copyright_for_accuracy: str = ""
    resolved_copyright: str = ""


def _resolve_authoritative_values(
    row: response_parser.InputRow,
    row_plan: response_parser.RowPlan,
    result: response_parser.QueryResult,
    verification: response_parser.VerificationResult,
) -> tuple[str, str, str]:
    """Resolve row values once so precedence logic stays centralized.

    Returns (resolved_license_name, resolved_license_url, inferred_license_for_accuracy).
    """
    input_license = str(row.extra.get("license_name", ""))
    input_url = str(row.extra.get("license_code_url", ""))

    input_license_present = not response_parser.is_value_missing(input_license)
    input_url_present = not response_parser.is_value_missing(input_url)

    resolved_license_name = input_license if input_license_present else verification.final_license
    resolved_license_url = input_url if input_url_present else result.license_url

    inferred_license_for_accuracy = verification.final_license if row_plan.need_license else ""
    return resolved_license_name, resolved_license_url, inferred_license_for_accuracy


def _resolve_copyright_for_output(
    row: response_parser.InputRow,
    row_plan: response_parser.RowPlan,
    copyright_result: response_parser.CopyrightResult | None,
) -> tuple[str, str]:
    """Resolve copyright values once so precedence logic stays centralized.

    ``copyright_for_accuracy`` is the value produced by this row's own
    extraction step (empty when extraction did not run), used to score
    against the input baseline independent of output precedence -- this stays
    meaningful even when ``force_copyright_extraction`` re-extracts over an
    already-provided input value.

    ``resolved_copyright`` mirrors the license precedence rule: the input
    copyright wins when present, and the extraction result only fills a gap.

    Returns (copyright_for_accuracy, resolved_copyright).
    """
    input_copyright = str(row.extra.get("copyright", ""))
    input_copyright_present = not response_parser.is_value_missing(input_copyright)
    produced_copyright = copyright_result.copyright if copyright_result else ""

    copyright_for_accuracy = produced_copyright if row_plan.need_copyright else ""
    resolved_copyright = input_copyright if input_copyright_present else produced_copyright
    return copyright_for_accuracy, resolved_copyright


def _read_downloaded_license_text(
    responses_dir: Path,
    fetch_result: license_fetcher.LicenseFetchResult,
) -> str | None:
    if (
        fetch_result.source != license_fetcher.FETCH_SOURCE_DOWNLOADED
        or not fetch_result.path.strip()
    ):
        return None
    abs_path = responses_dir.parent / fetch_result.path
    if not abs_path.exists() or not abs_path.is_file():
        return None
    try:
        return abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


async def process_row(
    infer_sem: asyncio.Semaphore,
    judge_sem: asyncio.Semaphore,
    fetch_sem: asyncio.Semaphore,
    gpt_client: Gpt41Client,
    equality_judge_client: EqualityJudgeClient,
    row: response_parser.InputRow,
    model: str,
    responses_dir: Path,
    *,
    row_plan: response_parser.RowPlan | None = None,
    force_license_inference: bool = False,
    force_copyright_extraction: bool = False,
    copyright_infer_sem: asyncio.Semaphore | None = None,
) -> ProcessedRow:
    """Execute one row according to the row plan while preserving precedence."""
    plan = row_plan or build_row_plan(
        row,
        force_license_inference=force_license_inference,
        force_copyright_extraction=force_copyright_extraction,
    )
    # The copyright-inference fallback gets its own pool so heavy license
    # inference cannot starve it; fall back to the license pool when a caller
    # (e.g. a unit test) does not supply a dedicated one.
    copyright_infer_sem = copyright_infer_sem or infer_sem

    comp = row.component_name
    _debug_log.info(
        "ROW start %s | inference=%s license=%s url=%s copyright=%s download=%s",
        comp, plan.need_inference, plan.need_license, plan.need_url,
        plan.need_copyright, plan.need_download,
    )

    input_license = str(row.extra.get("license_name", ""))
    input_url = str(row.extra.get("license_code_url", ""))
    input_copyright = str(row.extra.get("copyright", ""))

    if plan.need_inference:
        _debug_log.info("ROW %s | inference CALL start", comp)
        raw, infer_meta = await client.query_claude(
            infer_sem,
            row.lib_name,
            row.version,
            row.purl,
            model,
            need_license=plan.need_license,
            need_url=plan.need_url,
        )
        result = response_parser.parse_response(
            raw,
            infer_meta.elapsed_s,
        )
        result.inferencer_meta = infer_meta
        _debug_log.info(
            "ROW %s | inference CALL done in %.1fs (empty=%s license=%r)",
            comp, infer_meta.elapsed_s, not raw, result.predicted_license,
        )
    else:
        result = response_parser.QueryResult(
            predicted_license=input_license,
            license_url=input_url,
            reasoning="",
            raw_response="",
            elapsed_s=0.0,
        )
        raw = ""

    if not plan.need_license and response_parser.is_value_missing(result.predicted_license):
        result.predicted_license = input_license
    if not plan.need_url and response_parser.is_value_missing(result.license_url):
        result.license_url = input_url

    should_run_judge = plan.need_license and (
        plan.should_judge_license or force_license_inference
    )
    if should_run_judge:
        _debug_log.info("ROW %s | judge CALL start", comp)
        verification = await verifier.verify_consistency(
            gpt_client,
            judge_sem,
            result.predicted_license,
            result.reasoning,
            parse_error=result.parse_error,
        )
        _debug_log.info("ROW %s | judge CALL done verdict=%s", comp, verification.verdict)
    else:
        trusted_license = result.predicted_license if plan.need_license else input_license
        verification = response_parser.VerificationResult.skipped(trusted_license)

    resolved_license_name, resolved_license_url, inferred_for_accuracy = _resolve_authoritative_values(
        row,
        plan,
        result,
        verification,
    )

    if plan.need_download:
        slug = output.make_slug(row.component_name)
        download_url = result.license_url if plan.need_url else input_url
        _debug_log.info("ROW %s | fetch CALL start url=%s", comp, download_url)
        async with fetch_sem:
            fetch_result = await asyncio.to_thread(
                license_fetcher.fetch_license_file,
                download_url,
                responses_dir,
                slug,
                purl=row.purl,
                timeout_s=config.FETCH_TIMEOUT_S,
            )
        _debug_log.info(
            "ROW %s | fetch CALL done source=%s error=%s",
            comp, fetch_result.source, fetch_result.error,
        )
    else:
        fetch_result = license_fetcher.LicenseFetchResult.missing("download_not_needed")

    if plan.need_copyright:
        if fetch_result.source == license_fetcher.FETCH_SOURCE_DOWNLOADED:
            license_text = _read_downloaded_license_text(responses_dir, fetch_result)
            if license_text is None:
                copyright_result = response_parser.CopyrightResult(
                    copyright=config.COPYRIGHT_UNKNOWN,
                    reason=config.COPYRIGHT_REASON_NO_FILE,
                    raw_response="",
                    elapsed_s=0.0,
                    attempt_count=0,
                    extract_meta=None,
                )
            else:
                _debug_log.info("ROW %s | copyright EXTRACT start", comp)
                copyright_result = await copyright_extractor.extract_copyright(
                    gpt_client,
                    judge_sem,
                    license_text,
                )
                _debug_log.info(
                    "ROW %s | copyright EXTRACT done reason=%s", comp, copyright_result.reason
                )
        else:
            copyright_result = response_parser.CopyrightResult(
                copyright=config.COPYRIGHT_UNKNOWN,
                reason=fetch_result.error or config.COPYRIGHT_REASON_NO_FILE,
                raw_response="",
                elapsed_s=0.0,
                attempt_count=0,
                extract_meta=None,
            )

        if copyright_result.copyright == config.COPYRIGHT_UNKNOWN:
            # File-based extraction found no holder. npm's canonical holder
            # lives in the registry, not the LICENSE file, so try it before
            # giving up -- this is a no-op for non-npm purls.
            _debug_log.info("ROW %s | npm_author CALL start", comp)
            async with fetch_sem:
                npm_author = await asyncio.to_thread(
                    license_fetcher.fetch_npm_author,
                    row.purl,
                )
            _debug_log.info("ROW %s | npm_author CALL done found=%s", comp, bool(npm_author))
            if npm_author:
                copyright_result = response_parser.CopyrightResult(
                    copyright=f"Copyright (c) {npm_author}",
                    reason=config.COPYRIGHT_REASON_NPM_AUTHOR,
                    raw_response="",
                    elapsed_s=0.0,
                    attempt_count=0,
                    extract_meta=None,
                )

        if copyright_result.copyright == config.COPYRIGHT_UNKNOWN:
            # Neither the LICENSE file nor (for npm) the registry author
            # yielded a holder. Last resort: ask a web-enabled Claude call
            # directly for the copyright holder. Bottom of the ladder -- only
            # ever fills a remaining gap, never overrides a real result above.
            _debug_log.info("ROW %s | copyright INFER CALL start (web)", comp)
            inferred = await copyright_extractor.infer_copyright(
                copyright_infer_sem,
                row.lib_name,
                row.version,
                row.purl,
                model,
            )
            _debug_log.info(
                "ROW %s | copyright INFER CALL done in %.1fs reason=%s",
                comp, inferred.elapsed_s, inferred.reason,
            )
            if inferred.copyright != config.COPYRIGHT_UNKNOWN:
                copyright_result = inferred
    else:
        copyright_result = response_parser.CopyrightResult(
            copyright=input_copyright,
            reason=config.COPYRIGHT_REASON_INPUT_VALUE,
            raw_response="",
            elapsed_s=0.0,
            attempt_count=0,
            extract_meta=None,
        )

    _debug_log.info("ROW done %s | copyright_reason=%s", comp, copyright_result.reason)
    copyright_for_accuracy, resolved_copyright = _resolve_copyright_for_output(
        row,
        plan,
        copyright_result,
    )

    return ProcessedRow(
        raw_response=raw,
        row_plan=plan,
        query_result=result,
        verification=verification,
        fetch_result=fetch_result,
        resolved_license_name=resolved_license_name,
        resolved_license_url=resolved_license_url,
        inferred_license_for_accuracy=inferred_for_accuracy,
        copyright_result=copyright_result,
        copyright_for_accuracy=copyright_for_accuracy,
        resolved_copyright=resolved_copyright,
    )


def _build_process_row_task(
    infer_sem: asyncio.Semaphore,
    judge_sem: asyncio.Semaphore,
    fetch_sem: asyncio.Semaphore,
    gpt_client: Gpt41Client,
    equality_judge_client: EqualityJudgeClient,
    row: response_parser.InputRow,
    model: str,
    responses_dir: Path,
    row_plan: response_parser.RowPlan,
    force_license_inference: bool,
    force_copyright_extraction: bool,
    copyright_infer_sem: asyncio.Semaphore,
) -> asyncio.Task:
    """Build a process_row task."""
    return asyncio.create_task(
        process_row(
            infer_sem,
            judge_sem,
            fetch_sem,
            gpt_client,
            equality_judge_client,
            row,
            model,
            responses_dir,
            row_plan=row_plan,
            force_license_inference=force_license_inference,
            force_copyright_extraction=force_copyright_extraction,
            copyright_infer_sem=copyright_infer_sem,
        )
    )


def _classify_row_outcome(
    row_plan: response_parser.RowPlan,
    result: response_parser.QueryResult,
    verification: response_parser.VerificationResult,
) -> str:
    if not row_plan.need_inference:
        return response_parser.OUTCOME_OK
    return response_parser.classify_outcome(result, verification)


def _copyright_from_input_row(row: response_parser.InputRow) -> response_parser.CopyrightResult | None:
    input_copyright = str(row.extra.get("copyright", ""))
    if response_parser.is_value_missing(input_copyright):
        return None
    return response_parser.CopyrightResult(
        copyright=input_copyright,
        reason=config.COPYRIGHT_REASON_INPUT_VALUE,
        raw_response="",
        elapsed_s=0.0,
        attempt_count=0,
        extract_meta=None,
    )


def _resolve_cached_copyright(
    row: response_parser.InputRow,
    cached: cache_store.CacheEntry,
) -> response_parser.CopyrightResult | None:
    return cached.copyright_result or _copyright_from_input_row(row)


def _accumulate_cost(
    *,
    meta: CallMeta | None,
    cache_hit: bool,
    live_total: float,
    saved_total: float,
    unknown_live_calls: int,
) -> tuple[float, float, int]:
    if meta and meta.cost_usd is not None:
        if cache_hit:
            saved_total += meta.cost_usd
        else:
            live_total += meta.cost_usd
    elif meta and not cache_hit:
        unknown_live_calls += 1
    return live_total, saved_total, unknown_live_calls


async def fetch_cached_license_file(
    fetch_sem: asyncio.Semaphore,
    row: response_parser.InputRow,
    license_url: str,
    responses_dir: Path,
) -> license_fetcher.LicenseFetchResult:
    slug = output.make_slug(row.component_name)
    async with fetch_sem:
        return await asyncio.to_thread(
            license_fetcher.fetch_license_file,
            license_url,
            responses_dir,
            slug,
            purl=row.purl,
            timeout_s=config.FETCH_TIMEOUT_S,
        )


async def run(
    input_csv: Path,
    out_dir: Path,
    max_workers: int,
    model: str,
    cache_read_path: Path | None,
    cache_write_path: Path | None,
    run_name: str | None = None,
    force_license_inference: bool = False,
    force_copyright_extraction: bool = False,
    run_config_path: Path | None = None,
) -> None:
    responses_dir = out_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)
    run_id = out_dir.name
    _setup_debug_log(out_dir)

    with open(input_csv, newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))

    rows = [response_parser.InputRow.from_csv_row(r) for r in raw_rows]
    total = len(rows)
    _debug_log.info(
        "RUN start id=%s model=%s workers=%s force_license=%s force_copyright=%s components=%s",
        run_id, model, max_workers, force_license_inference,
        force_copyright_extraction, total,
    )
    out_csv = out_dir / paths.make_results_csv_name(model, total, run_name)
    enriched_csv = out_dir / paths.make_enriched_csv_name(input_csv)
    fieldnames = list(raw_rows[0].keys()) + RESULT_EXTRA_FIELDS
    cache_entries = (
        cache_store.load_cache(cache_read_path, model=model)
        if cache_read_path is not None else {}
    )
    cache_hits = 0
    partial_hits = 0
    live_rows = 0
    chosen_parameters = {
        "paths": {
            "input_csv": str(input_csv),
            "output_dir": str(out_dir),
            "output_results_csv": str(out_csv),
            "output_enriched_csv": str(enriched_csv),
            "output_responses_dir": str(responses_dir),
            "cache_read_path": None if cache_read_path is None else str(cache_read_path),
            "cache_write_path": None if cache_write_path is None else str(cache_write_path),
            "run_config_file": None if run_config_path is None else str(run_config_path),
        },
        "run_id": run_id,
        "run_name": run_name,
        "model": model,
        "workers": {
            "inference_workers": max_workers,
            "judge_workers": config.JUDGE_MAX_WORKERS,
            "fetch_workers": config.FETCH_MAX_WORKERS,
        },
        "forcing": {
            "license": force_license_inference,
            "copyright": force_copyright_extraction,
        },
        "components": total,
    }

    print("Run parameters")
    print(f"  run-id:   {chosen_parameters['run_id']}")
    print(f"  input:    {chosen_parameters['paths']['input_csv']}")
    print(f"  output:   {chosen_parameters['paths']['output_dir']}")
    print(f"  results:  {chosen_parameters['paths']['output_results_csv']}")
    print(f"  responses:{chosen_parameters['paths']['output_responses_dir']}")
    print(f"  cache-r:  {chosen_parameters['paths']['cache_read_path']}")
    print(f"  cache-w:  {chosen_parameters['paths']['cache_write_path']}")
    print(f"  run-config: {chosen_parameters['paths']['run_config_file']}")
    print(f"  model:    {chosen_parameters['model']}")
    print(
        f"  workers:  {chosen_parameters['workers']['inference_workers']} "
        f"(judge: {chosen_parameters['workers']['judge_workers']}, "
        f"fetch: {chosen_parameters['workers']['fetch_workers']})"
    )
    print(f"  force-license-inference: {chosen_parameters['forcing']['license']}")
    print(f"  force-copyright-extraction: {chosen_parameters['forcing']['copyright']}")
    print(f"  components: {chosen_parameters['components']}")
    print()
    print(f"Processing {total} libraries (max {max_workers} concurrent)...")
    total_start = time.monotonic()
    start_dt = datetime.now(UTC)

    infer_sem = asyncio.Semaphore(max_workers)
    judge_sem = asyncio.Semaphore(config.JUDGE_MAX_WORKERS)
    fetch_sem = asyncio.Semaphore(config.FETCH_MAX_WORKERS)
    copyright_infer_sem = asyncio.Semaphore(config.COPYRIGHT_INFER_MAX_WORKERS)
    gpt_client = Gpt41Client()
    equality_judge_client = EqualityJudgeClient()
    lic_eq_extra: dict = {}
    cp_eq_extra: dict = {}

    async def _lic_judge(expected: str, actual: str) -> tuple[bool, CallMeta | None]:
        r = await equality_judge_client.are_identical(expected, actual, kind=config.EQUALITY_JUDGE_KIND_LICENSE)
        lic_eq_extra["query"] = r.query
        lic_eq_extra["raw_response"] = r.raw_response
        return r.verdict, r.meta

    async def _cp_judge(expected: str, actual: str) -> tuple[bool, CallMeta | None]:
        r = await equality_judge_client.are_identical(expected, actual, kind=config.EQUALITY_JUDGE_KIND_COPYRIGHT)
        cp_eq_extra["query"] = r.query
        cp_eq_extra["raw_response"] = r.raw_response
        return r.verdict, r.meta

    tasks: dict[int, asyncio.Task] = {}
    row_plans: dict[int, response_parser.RowPlan] = {}
    cached_by_index: dict[int, cache_store.CacheEntry] = {}
    file_only_by_index: dict[int, asyncio.Task] = {}
    for index, row in enumerate(rows):
        row_plan = build_row_plan(
            row,
            force_license_inference=force_license_inference,
            force_copyright_extraction=force_copyright_extraction,
        )
        row_plans[index] = row_plan
        cached = cache_entries.get(cache_store.cache_key_for_row(row))
        if cached is None:
            live_rows += 1
            tasks[index] = _build_process_row_task(
                infer_sem,
                judge_sem,
                fetch_sem,
                gpt_client,
                equality_judge_client,
                row,
                model,
                responses_dir,
                row_plan,
                force_license_inference,
                force_copyright_extraction,
                copyright_infer_sem,
            )
            continue
        cached_by_index[index] = cached
        if cache_store.is_file_cached(cache_read_path, cached):
            cache_hits += 1
            continue
        partial_hits += 1
        file_only_by_index[index] = asyncio.create_task(
            fetch_cached_license_file(
                fetch_sem,
                row,
                cached.result.license_url,
                responses_dir,
            )
        )

    _debug_log.info(
        "SCHEDULE live=%s full_cache=%s partial_cache=%s",
        live_rows, cache_hits, partial_hits,
    )
    print(f"\r  {output.progress_bar(0, total)}  starting…", end="", flush=True)

    outcomes_by_reason: dict[str, int] = {name: 0 for name in response_parser.ALL_OUTCOMES}
    license_file_outcomes: dict[str, int] = {
        license_fetcher.FETCH_SOURCE_DOWNLOADED: 0,
        license_fetcher.FETCH_SOURCE_MISSING: 0,
    }
    license_file_errors: dict[str, int] = {}

    # Live inferencer spend this run, and money saved by cache hits
    cost_inferencer: float = 0.0
    saved_inferencer: float = 0.0
    unknown_cost_inferencer: int = 0

    # Live judge spend this run, and money saved by cache hits
    cost_judge: float = 0.0
    saved_judge: float = 0.0
    unknown_cost_judge: int = 0

    # Live eq judge spend this run (always live, even on cache hits)
    cost_eq: float = 0.0
    unknown_cost_eq: int = 0

    # Live copyright-eq judge spend this run (always live, even on cache hits)
    cost_cp_eq: float = 0.0
    unknown_cost_cp_eq: int = 0

    # Copyright extraction spend this run
    cost_copyright: float = 0.0
    saved_copyright: float = 0.0
    unknown_cost_copyright: int = 0
    copyright_outcomes: dict[str, int] = {
        "extracted": 0,
        config.COPYRIGHT_REASON_INPUT_VALUE: 0,
        "unknown": 0,
        "missing": 0,
    }
    copyright_reasons: dict[str, int] = {}

    num_identical_licenses: int = 0
    num_identical_copyrights: int = 0

    # Per-field accuracy, scored only over rows where the input CSV supplies
    # ground truth for that field (UNKNOWN predictions count as incorrect).
    rows_with_license_ground_truth: int = 0
    license_ground_truth_correct: int = 0
    rows_with_copyright_ground_truth: int = 0
    copyright_ground_truth_correct: int = 0

    # Joint license+copyright accuracy matrix, scored only over rows where the
    # input CSV supplies ground truth for *both* license and copyright (UNKNOWN
    # predictions count as incorrect via LicenseMatchResult/CopyrightMatchResult).
    rows_with_both_ground_truth: int = 0
    both_correct: int = 0
    license_correct_copyright_wrong: int = 0
    license_wrong_copyright_correct: int = 0
    both_wrong: int = 0

    enriched_values: dict[int, tuple[str, str, str]] = {}

    # Phase 1 -- advance the progress bar as live and partial-cache tasks finish,
    # in completion order. The in-order write pass below awaits rows strictly by
    # input index, so a single slow early row (e.g. row 1) would otherwise pin
    # the bar there even while dozens of later rows are already done. Exceptions
    # are swallowed here and re-raised deterministically by the write pass, which
    # is the sole owner of results.csv ordering.
    pending_tasks = [*tasks.values(), *file_only_by_index.values()]
    if pending_tasks:
        completed = cache_hits  # fully-cached rows need no await
        print(f"\r  {output.progress_bar(completed, total)}  processing…", end="", flush=True)
        for finished in asyncio.as_completed(pending_tasks):
            try:
                await finished
            except Exception:
                pass
            completed += 1
            print(f"\r  {output.progress_bar(completed, total)}  processing…", end="", flush=True)

    try:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            _debug_log.info("DRAIN loop start over %d rows (input order)", total)

            for i, row in enumerate(rows, start=1):
                row_index = i - 1
                row_plan = row_plans[row_index]
                cached = cached_by_index.get(row_index)
                cache_hit = cached is not None
                if row_index in file_only_by_index:
                    result = cached.result
                    verification = cached.verification
                    _debug_log.info("DRAIN await partial-cache row %d/%d %s", i, total, row.component_name)
                    fetch_result = await file_only_by_index[row_index]
                    _debug_log.info("DRAIN done partial-cache row %d/%d %s", i, total, row.component_name)
                    outcome = cached.outcome or _classify_row_outcome(row_plan, result, verification)
                    partial_copyright_result = _resolve_cached_copyright(row, cached)
                    if fetch_result.source == license_fetcher.FETCH_SOURCE_DOWNLOADED:
                        cache_entries[cache_store.cache_key_for_row(row)] = cache_store.make_cache_entry(
                            row,
                            result,
                            verification,
                            fetch_result,
                            run_id=run_id,
                            outcome=outcome,
                            copyright_result=partial_copyright_result,
                        )
                    resolved_license_name, resolved_license_url, inferred_for_accuracy = _resolve_authoritative_values(
                        row,
                        row_plan,
                        result,
                        verification,
                    )
                    copyright_for_accuracy, resolved_copyright = _resolve_copyright_for_output(
                        row,
                        row_plan,
                        partial_copyright_result,
                    )
                    processed = ProcessedRow(
                        raw_response="",
                        row_plan=row_plan,
                        query_result=result,
                        verification=verification,
                        fetch_result=fetch_result,
                        resolved_license_name=resolved_license_name,
                        resolved_license_url=resolved_license_url,
                        inferred_license_for_accuracy=inferred_for_accuracy,
                        copyright_result=partial_copyright_result,
                        copyright_for_accuracy=copyright_for_accuracy,
                        resolved_copyright=resolved_copyright,
                    )
                elif cached is not None:
                    result = cached.result
                    verification = cached.verification
                    fetch_result = cache_store.restore_cached_file(
                        cache_read_path,
                        out_dir,
                        row.component_name,
                        cached.fetch_result,
                    )
                    outcome = cached.outcome or _classify_row_outcome(row_plan, result, verification)
                    cached_copyright_result = _resolve_cached_copyright(row, cached)
                    resolved_license_name, resolved_license_url, inferred_for_accuracy = _resolve_authoritative_values(
                        row,
                        row_plan,
                        result,
                        verification,
                    )
                    copyright_for_accuracy, resolved_copyright = _resolve_copyright_for_output(
                        row,
                        row_plan,
                        cached_copyright_result,
                    )
                    processed = ProcessedRow(
                        raw_response="",
                        row_plan=row_plan,
                        query_result=result,
                        verification=verification,
                        fetch_result=fetch_result,
                        resolved_license_name=resolved_license_name,
                        resolved_license_url=resolved_license_url,
                        inferred_license_for_accuracy=inferred_for_accuracy,
                        copyright_result=cached_copyright_result,
                        copyright_for_accuracy=copyright_for_accuracy,
                        resolved_copyright=resolved_copyright,
                    )
                else:
                    _debug_log.info("DRAIN await live row %d/%d %s", i, total, row.component_name)
                    processed = await tasks[row_index]
                    _debug_log.info("DRAIN done live row %d/%d %s", i, total, row.component_name)
                    result = processed.query_result
                    verification = processed.verification
                    fetch_result = processed.fetch_result
                    outcome = _classify_row_outcome(row_plan, result, verification)
                    # Cache all OUTCOME_OK rows, including those with fully-provided
                    # input values (no inference), to preserve copyright extraction
                    # results and avoid redundant re-processing on subsequent runs.
                    if outcome == response_parser.OUTCOME_OK:
                        cache_entries[cache_store.cache_key_for_row(row)] = cache_store.make_cache_entry(
                            row,
                            result,
                            verification,
                            fetch_result,
                            run_id=run_id,
                            outcome=outcome,
                            copyright_result=processed.copyright_result,
                        )

                result = processed.query_result
                verification = processed.verification
                fetch_result = processed.fetch_result

                outcomes_by_reason[outcome] += 1
                license_file_outcomes[fetch_result.source] = license_file_outcomes.get(fetch_result.source, 0) + 1
                if fetch_result.error:
                    license_file_errors[fetch_result.error] = license_file_errors.get(fetch_result.error, 0) + 1

                cost_inferencer, saved_inferencer, unknown_cost_inferencer = _accumulate_cost(
                    meta=result.inferencer_meta,
                    cache_hit=cache_hit,
                    live_total=cost_inferencer,
                    saved_total=saved_inferencer,
                    unknown_live_calls=unknown_cost_inferencer,
                )
                cost_judge, saved_judge, unknown_cost_judge = _accumulate_cost(
                    meta=verification.judge_meta,
                    cache_hit=cache_hit,
                    live_total=cost_judge,
                    saved_total=saved_judge,
                    unknown_live_calls=unknown_cost_judge,
                )

                lic_eq_extra.clear()
                cp_eq_extra.clear()
                match_result = await license_matcher.compare_licenses(
                    str(row.extra.get("license_name", "")),
                    processed.inferred_license_for_accuracy,
                    llm_judge=_lic_judge,
                )
                if match_result.equal:
                    num_identical_licenses += 1

                # Accumulate eq judge costs (always live, even on cache hits)
                if match_result.eq_meta and match_result.eq_meta.cost_usd is not None:
                    cost_eq += match_result.eq_meta.cost_usd
                elif match_result.eq_meta:
                    unknown_cost_eq += 1

                # Independent copyright score: same exact/normalized/LLM ladder,
                # scored against the input copyright baseline.
                cp_match_result = await copyright_matcher.compare_copyrights(
                    str(row.extra.get("copyright", "")),
                    processed.copyright_for_accuracy,
                    llm_judge=_cp_judge,
                )
                if cp_match_result.equal:
                    num_identical_copyrights += 1

                # Accumulate copyright-eq judge costs (always live, even on cache hits)
                if cp_match_result.eq_meta and cp_match_result.eq_meta.cost_usd is not None:
                    cost_cp_eq += cp_match_result.eq_meta.cost_usd
                elif cp_match_result.eq_meta:
                    unknown_cost_cp_eq += 1

                has_license_ground_truth = not response_parser.is_value_missing(
                    str(row.extra.get("license_name", ""))
                )
                has_copyright_ground_truth = not response_parser.is_value_missing(
                    str(row.extra.get("copyright", ""))
                )
                if has_license_ground_truth:
                    rows_with_license_ground_truth += 1
                    if match_result.equal:
                        license_ground_truth_correct += 1
                if has_copyright_ground_truth:
                    rows_with_copyright_ground_truth += 1
                    if cp_match_result.equal:
                        copyright_ground_truth_correct += 1
                if has_license_ground_truth and has_copyright_ground_truth:
                    rows_with_both_ground_truth += 1
                    if match_result.equal and cp_match_result.equal:
                        both_correct += 1
                    elif match_result.equal and not cp_match_result.equal:
                        license_correct_copyright_wrong += 1
                    elif not match_result.equal and cp_match_result.equal:
                        license_wrong_copyright_correct += 1
                    else:
                        both_wrong += 1

                # Accumulate copyright extraction costs
                copyright_result = processed.copyright_result
                if copyright_result is None:
                    copyright_outcomes["missing"] += 1
                    reason_key = "missing_from_cache"
                    copyright_reasons[reason_key] = copyright_reasons.get(reason_key, 0) + 1
                else:
                    if copyright_result.reason == config.COPYRIGHT_REASON_INPUT_VALUE:
                        copyright_outcomes[config.COPYRIGHT_REASON_INPUT_VALUE] += 1
                    elif copyright_result.copyright == config.COPYRIGHT_UNKNOWN:
                        copyright_outcomes["unknown"] += 1
                    else:
                        copyright_outcomes["extracted"] += 1

                    reason_key = copyright_result.reason or "unknown_reason"
                    copyright_reasons[reason_key] = copyright_reasons.get(reason_key, 0) + 1

                    if copyright_result.extract_meta and copyright_result.extract_meta.cost_usd is not None:
                        if cache_hit:
                            saved_copyright += copyright_result.extract_meta.cost_usd
                        else:
                            cost_copyright += copyright_result.extract_meta.cost_usd
                    elif copyright_result.extract_meta and not cache_hit:
                        unknown_cost_copyright += 1
                    elif cache_hit and cached is not None and cached.copyright_cost_usd is not None:
                        saved_copyright += cached.copyright_cost_usd

                slug = output.make_slug(row.component_name)
                raw_response = processed.raw_response
                parsed_dict = None if result.parse_error or not raw_response else {
                    "license": result.predicted_license,
                    "license_url": result.license_url,
                    "reasoning": result.reasoning,
                }
                output.save_response(
                    responses_dir,
                    slug,
                    raw_response,
                    parsed_dict,
                    verification,
                    fetch_result,
                    inferencer_meta=result.inferencer_meta,
                    eq_meta=match_result.eq_meta,
                    cp_eq_meta=cp_match_result.eq_meta,
                    copyright_result=copyright_result,
                    lic_eq_query=lic_eq_extra.get("query", ""),
                    lic_eq_raw=lic_eq_extra.get("raw_response", ""),
                    cp_eq_query=cp_eq_extra.get("query", ""),
                    cp_eq_raw=cp_eq_extra.get("raw_response", ""),
                )

                writer.writerow(
                    output.build_output_row(
                        row,
                        result,
                        verification,
                        fetch_result,
                        cache_hit=cache_hit,
                        outcome=outcome,
                        lic_eq=match_result.csv_fields()["lic_eq"],
                        eq_kind=match_result.csv_fields()["eq_kind"],
                        lic_eq_raw=lic_eq_extra.get("raw_response", ""),
                        cp_eq=cp_match_result.csv_fields()["cp_eq"],
                        cp_eq_kind=cp_match_result.csv_fields()["cp_eq_kind"],
                        cp_eq_raw=cp_eq_extra.get("raw_response", ""),
                        inferencer_meta=result.inferencer_meta,
                        judge_meta=verification.judge_meta,
                        eq_meta=match_result.eq_meta,
                        cp_eq_meta=cp_match_result.eq_meta,
                        copyright_result=copyright_result,
                    )
                )
                f.flush()
                _debug_log.info("DRAIN wrote row %d/%d %s", i, total, row.component_name)
                license_was_provided = not response_parser.is_value_missing(
                    str(row.extra.get("license_name", ""))
                )
                enriched_license_name = (
                    processed.resolved_license_name
                    if license_was_provided or outcome == response_parser.OUTCOME_OK
                    else verifier.UNKNOWN_LICENSE
                )
                enriched_copyright = processed.resolved_copyright
                enriched_values[row_index] = (
                    enriched_license_name,
                    processed.resolved_license_url,
                    enriched_copyright,
                )

                wall = time.monotonic() - total_start
                rate = i / wall if wall > 0 else 0
                eta_s = (total - i) / rate if rate > 0 and i < total else 0
                eta_str = f"ETA {eta_s:.0f}s" if i < total else f"done in {wall:.0f}s"
                suffix = output.format_status_suffix(row, result, verification)
                print(
                    f"\r  {output.progress_bar(i, total)}  {suffix:<60}  {eta_str:<15}",
                    end="",
                    flush=True,
                )

        enriched_fieldnames = output.build_enriched_fieldnames(list(raw_rows[0].keys()))
        with open(enriched_csv, "w", newline="", encoding="utf-8") as ef:
            ewriter = csv.DictWriter(ef, fieldnames=enriched_fieldnames)
            ewriter.writeheader()
            for idx, raw_row in enumerate(raw_rows):
                final_license, license_url, copyright = enriched_values[idx]
                ewriter.writerow(output.build_enriched_row(raw_row, final_license, license_url, copyright))
    finally:
        await gpt_client.aclose()
        await equality_judge_client.aclose()

    total_elapsed = time.monotonic() - total_start
    end_dt = datetime.now(UTC)
    if cache_write_path is not None:
        cache_store.write_cache(cache_write_path, cache_entries, run_root=out_dir)

    def _fmt_utc(dt: datetime) -> str:
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    hours, remainder = divmod(int(total_elapsed), 3600)
    minutes, seconds = divmod(remainder, 60)
    num_ok = outcomes_by_reason[response_parser.OUTCOME_OK]
    num_unknown = total - num_ok
    num_failures = sum(
        outcomes_by_reason[name] for name in response_parser.FAILURE_OUTCOMES
    )
    # Any non-"ok" outcome downgrades the final license to UNKNOWN (see
    # verifier.verify_consistency / response_parser.classify_outcome), so the
    # UNKNOWN license count is simply everything that isn't "ok".
    copyright_unknown_total = copyright_outcomes["unknown"] + copyright_outcomes["missing"]
    total_data_cost = cost_inferencer + cost_judge + cost_copyright
    total_elapsed_reported = round(total_elapsed, 3)

    def _pct(value: int, denom: int) -> float | None:
        return round(value / denom, 6) if denom else None

    def _bucket(value: int, denom: int) -> dict:
        return {"total": value, "pct": _pct(value, denom)}

    run_params = dict(chosen_parameters)
    run_params["start_time_utc"] = _fmt_utc(start_dt)
    run_params["end_time_utc"] = _fmt_utc(end_dt)
    run_params["cache"] = {
        "full_hits": cache_hits,
        "partial_hits": partial_hits,
        "total_hits": cache_hits + partial_hits,
        "live_queries": live_rows,
    }

    licenses = {
        "outcomes": outcomes_by_reason,
        "summary": {"ok": num_ok, "unknown": num_unknown, "failures": num_failures},
        "file_fetch": {"outcomes": license_file_outcomes, "errors": license_file_errors},
        "accuracy": {
            "evaluated_components": rows_with_license_ground_truth,
            "correct": _bucket(license_ground_truth_correct, rows_with_license_ground_truth),
            "wrong": _bucket(
                rows_with_license_ground_truth - license_ground_truth_correct,
                rows_with_license_ground_truth,
            ),
            "comparable_to_legacy": force_license_inference,
        },
    }

    copyright_section = {
        "outcomes": copyright_outcomes,
        "reasons": copyright_reasons,
        "accuracy": {
            "evaluated_components": rows_with_copyright_ground_truth,
            "correct": _bucket(copyright_ground_truth_correct, rows_with_copyright_ground_truth),
            "wrong": _bucket(
                rows_with_copyright_ground_truth - copyright_ground_truth_correct,
                rows_with_copyright_ground_truth,
            ),
            "comparable_to_legacy": force_copyright_extraction,
        },
    }

    costs = {
        "inference": {
            "total_usd": round(cost_inferencer, 6),
            "avg_per_row_usd": round(cost_inferencer / total, 6) if total else None,
            "saved_by_cache_usd": round(saved_inferencer, 6),
            "unknown_cost_calls": unknown_cost_inferencer,
        },
        "consistency_judge": {
            "total_usd": round(cost_judge, 6),
            "avg_per_row_usd": round(cost_judge / total, 6) if total else None,
            "saved_by_cache_usd": round(saved_judge, 6),
            "unknown_cost_calls": unknown_cost_judge,
        },
        "copyright_extraction": {
            "total_usd": round(cost_copyright, 6),
            "avg_per_row_usd": round(cost_copyright / total, 6) if total else None,
            "saved_by_cache_usd": round(saved_copyright, 6),
            "unknown_cost_calls": unknown_cost_copyright,
        },
        "equality_judges": {
            "license": {
                "total_usd": round(cost_eq, 6),
                "avg_per_row_usd": round(cost_eq / total, 6) if total else None,
                "unknown_cost_calls": unknown_cost_eq,
            },
            "copyright": {
                "total_usd": round(cost_cp_eq, 6),
                "avg_per_row_usd": round(cost_cp_eq / total, 6) if total else None,
                "unknown_cost_calls": unknown_cost_cp_eq,
            },
        },
        "total_usd": round(total_data_cost, 6),
        "avg_per_row_usd": round(total_data_cost / total, 6) if total else None,
    }

    bottom_line = {
        "cost": {
            "total_inference_usd": round(cost_inferencer, 6),
            "avg_per_row_inference_usd": round(cost_inferencer / total, 6) if total else None,
        },
        "time": {
            "total_seconds": total_elapsed_reported,
            "formatted": f"{hours}:{minutes:02d}:{seconds:02d}",
            "avg_seconds_per_row": round(total_elapsed_reported / total, 6) if total else None,
        },
        "unknown": {
            "licenses_unknown": _bucket(num_unknown, total),
            "copyrights_unknown": _bucket(copyright_unknown_total, total),
        },
        "accuracy": (
            {
                "evaluated_components": rows_with_both_ground_truth,
                "license_and_copyright_correct": _bucket(both_correct, rows_with_both_ground_truth),
                "license_correct_copyright_wrong": _bucket(
                    license_correct_copyright_wrong, rows_with_both_ground_truth
                ),
                "license_wrong_copyright_correct": _bucket(
                    license_wrong_copyright_correct, rows_with_both_ground_truth
                ),
                "license_and_copyright_wrong": _bucket(both_wrong, rows_with_both_ground_truth),
            }
            if rows_with_both_ground_truth
            else None
        ),
    }

    run_info = {
        "run_params": run_params,
        "licenses": licenses,
        "copyright": copyright_section,
        "costs": costs,
        "bottom_line": bottom_line,
    }
    run_info_path = out_dir / "run_info.json"
    run_info_path.write_text(json.dumps(run_info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"\nResults written to: {out_csv}")
    print(f"Run info written to: {run_info_path}")
    print(f"Total time: {total_elapsed:.2f}s")


async def main() -> None:
    _force_utf8_streams()
    args = cli.parse_args()
    _ensure_azure_auth_ready()

    if args.config is not None:
        config_path = paths.resolve_project_path(args.config)
        run_cfg = run_config.load_run_config(config_path)
    else:
        config_path = DEFAULT_RUN_CONFIG_PATH
        run_cfg = run_config.load_run_config(config_path, require_input_csv=False)

    input_csv = paths.resolve_project_path(args.input) if args.input is not None else run_cfg.input_csv
    if input_csv is None:
        sys.exit(
            "Input CSV is required. Provide --input CSV or set 'input_csv' in "
            "run_configs/default_config.json."
        )

    input_errors = paths.validate_input_csv(input_csv)
    if input_errors:
        sys.exit("Input CSV validation failed:\n" + "\n".join(input_errors))

    model = args.model if args.model is not None else run_cfg.model
    output_base = paths.resolve_project_path(args.output) if args.output is not None else run_cfg.output_base
    run_name = args.run_name if args.run_name is not None else run_cfg.run_name

    cache_read_arg = args.cache_read
    if cache_read_arg is None and run_cfg.cache_read is not None:
        cache_read_arg = str(run_cfg.cache_read)
    cache_write_arg = args.cache_write
    if cache_write_arg is None and run_cfg.cache_write is not None:
        cache_write_arg = str(run_cfg.cache_write)
    cache_read_path, cache_write_path = paths.resolve_cache_paths(
        cache_read_arg,
        cache_write_arg,
    )

    if args.workers is not None:
        workers = args.workers
    elif args.use_defaults:
        workers = paths.resolve_workers(None, input_csv, use_defaults=True)
    else:
        workers = run_cfg.workers

    out_dir = paths.create_run_dir(input_csv, output_base, model, run_name)
    shutil.copy2(config_path, out_dir / config_path.name)

    await run(
        input_csv,
        out_dir,
        workers,
        model,
        cache_read_path,
        cache_write_path,
        run_name,
        run_cfg.force_license_inference,
        run_cfg.force_copyright_extraction,
        run_config_path=config_path,
    )


if __name__ == "__main__":
    asyncio.run(main())
