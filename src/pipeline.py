"""Per-component pipeline and bounded asyncio worker pool."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from cache import read_cache, restore_license_file, write_cache
from claude_client import infer_license
from config import Config
from copyright import resolve_copyright
from download import fetch_license_file
from equality import compare_copyright, compare_name, compare_url_content
from eventlog import component_context, emit, log_op, slot_context
from gpt41_client import Gpt41Client
from input_csv import Component
from pricing import CallMeta
from results_csv import ResultsWriter
from scoring import grade_row

STORY_FILENAME = "story.txt"


@dataclass
class ComponentResult:
    component: Component
    inferred_license_name: str = "UNKNOWN"
    inferred_license_code_url: str = "UNKNOWN"
    inferred_copyright: str = "UNKNOWN"
    license_file_path: Path | None = None
    download_attempts: list[str] = field(default_factory=list)
    original_license_url: str = ""
    from_cache: bool = False
    is_eq_license_name: str = ""
    is_eq_license_code_url: str = ""
    is_eq_copyright: str = ""
    eq_license_name_reason: str = ""
    eq_license_code_url_reason: str = ""
    eq_copyright_reason: str = ""
    grades: dict[str, str] = field(default_factory=dict)
    license_meta: CallMeta = field(default_factory=CallMeta)
    copyright_meta: CallMeta = field(default_factory=CallMeta)
    eq_license_name_meta: CallMeta = field(default_factory=CallMeta)
    eq_license_code_url_meta: CallMeta = field(default_factory=CallMeta)
    eq_copyright_meta: CallMeta = field(default_factory=CallMeta)
    error: str = ""


def story_path(run_dir: Path, slug: str) -> Path:
    return run_dir / "per_component" / slug / STORY_FILENAME


def append_story(run_dir: Path, slug: str, line: str) -> None:
    path = story_path(run_dir, slug)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


async def process_component(
    comp: Component,
    run_dir: Path,
    model: str,
    client: Gpt41Client,
    *,
    cache_read: Path | None = None,
    cache_write: Path | None = None,
) -> ComponentResult:
    result = ComponentResult(component=comp)
    if not (comp.purl or "").strip():
        append_story(run_dir, comp.slug, "no purl")

    cached = read_cache(cache_read, comp.component_name)
    emit("cache", "event", kind="read", hit=cached is not None)
    if cached is not None:
        flat = restore_license_file(cached, run_dir, comp.slug)
        result.inferred_license_name = cached.inferred_license_name
        result.inferred_license_code_url = cached.inferred_license_code_url
        result.inferred_copyright = cached.inferred_copyright
        result.license_file_path = flat
        result.from_cache = True
        append_story(run_dir, comp.slug, "cache hit")
        return result

    t0 = time.perf_counter()
    async with log_op("license"):
        inferred = await infer_license(comp.purl, comp.lib_name, comp.version, model)
    # Fakes may still return a plain dict; real client returns (dict, CallMeta).
    if isinstance(inferred, tuple):
        data, result.license_meta = inferred
    else:
        data = inferred
    elapsed = time.perf_counter() - t0

    result.inferred_license_name = data["license_name"]
    result.inferred_license_code_url = data["license_code_url"]
    result.original_license_url = data["license_code_url"]
    append_story(
        run_dir,
        comp.slug,
        f"license: {data['reasoning']} attempts={data.get('attempts', '?')} "
        f"timing_s={elapsed:.3f}",
    )

    t1 = time.perf_counter()
    async with log_op("download"):
        dl = await fetch_license_file(
            data["license_code_url"], comp.purl, run_dir, comp.slug
        )
    dl_elapsed = time.perf_counter() - t1
    result.download_attempts = list(dl.attempts)
    for line in dl.attempts:
        append_story(run_dir, comp.slug, f"download: {line}")

    if dl.ok:
        result.inferred_license_code_url = dl.resolved_url
        result.license_file_path = dl.saved_path
        append_story(
            run_dir,
            comp.slug,
            f"download: chose {dl.resolved_url} timing_s={dl_elapsed:.3f}",
        )
    else:
        append_story(
            run_dir,
            comp.slug,
            f"download: failed ({dl.error or 'unknown'}) timing_s={dl_elapsed:.3f}",
        )

    text = ""
    if result.license_file_path is not None:
        text = result.license_file_path.read_text(encoding="utf-8", errors="replace")
    t2 = time.perf_counter()
    async with log_op("copyright"):
        cr = await resolve_copyright(
            client, text, comp.purl, comp.lib_name, comp.version, model
        )
    # Fakes may still return a plain dict; real resolver returns (dict, CallMeta).
    if isinstance(cr, tuple):
        data, result.copyright_meta = cr
    else:
        data = cr
    cr_elapsed = time.perf_counter() - t2
    result.inferred_copyright = data["copyright"]
    append_story(
        run_dir,
        comp.slug,
        f"copyright: {data['reasoning']} timing_s={cr_elapsed:.3f}",
    )

    write_cache(cache_write, comp.component_name, result)
    emit("cache", "event", kind="write")
    return result


async def apply_equality(
    result: ComponentResult,
    run_dir: Path,
    gt_columns: list[str],
    client: Gpt41Client | None,
) -> None:
    """Fill is_eq_* / reasons / grades when audit GT columns are present."""
    if not gt_columns:
        return
    extras = result.component.extras
    slug = result.component.slug

    if "license_name" in gt_columns:
        async with log_op("equality_name"):
            eq = await compare_name(
                result.inferred_license_name,
                extras.get("license_name", ""),
                client=client,
            )
        result.is_eq_license_name = eq.verdict
        result.eq_license_name_reason = eq.reason
        result.eq_license_name_meta = eq.meta
        append_story(run_dir, slug, f"is_eq_license_name={eq.verdict} ({eq.reason})")

    if "license_code_url" in gt_columns:
        async with log_op("equality_url"):
            eq = await compare_url_content(
                result.inferred_license_code_url,
                extras.get("license_code_url", ""),
                run_dir,
                slug,
                client=client,
            )
        result.is_eq_license_code_url = eq.verdict
        result.eq_license_code_url_reason = eq.reason
        result.eq_license_code_url_meta = eq.meta
        append_story(
            run_dir, slug, f"is_eq_license_code_url={eq.verdict} ({eq.reason})"
        )

    if "copyright" in gt_columns:
        async with log_op("equality_copyright"):
            eq = await compare_copyright(
                result.inferred_copyright,
                extras.get("copyright", ""),
                client=client,
            )
        result.is_eq_copyright = eq.verdict
        result.eq_copyright_reason = eq.reason
        result.eq_copyright_meta = eq.meta
        append_story(run_dir, slug, f"is_eq_copyright={eq.verdict} ({eq.reason})")

    result.grades = grade_row(result, gt_columns)


async def run_workers(
    config: Config,
    components: list[Component],
    run_dir: Path,
    writer: ResultsWriter,
    gt_columns: list[str] | None = None,
) -> list[ComponentResult]:
    gt_columns = list(gt_columns or [])
    client = Gpt41Client()
    sem = asyncio.Semaphore(config.workers)
    results: list[ComponentResult] = []
    # Free lanes emulate worker identity: the semaphore bounds concurrency but
    # gives no slot number, so we hand out an id on acquire for concurrency viz.
    free_slots = list(range(config.workers))

    async def one(comp: Component, comp_idx: int) -> ComponentResult:
        with component_context(comp_idx, comp.slug):
            emit("component", "queued")
            async with sem:
                slot = free_slots.pop()
                result = ComponentResult(component=comp)
                try:
                    with slot_context(slot):
                        try:
                            async with log_op("component"):
                                result = await process_component(
                                    comp,
                                    run_dir,
                                    config.model,
                                    client,
                                    cache_read=config.cache_read,
                                    cache_write=config.cache_write,
                                )
                                await apply_equality(
                                    result, run_dir, gt_columns, client
                                )
                        except Exception as exc:
                            detail = str(exc).splitlines()[0].strip()
                            result.error = (
                                f"{type(exc).__name__}: {detail}"
                                if detail
                                else type(exc).__name__
                            )
                            append_story(run_dir, comp.slug, f"error: {result.error}")
                finally:
                    free_slots.append(slot)
            return result

    tasks = [
        asyncio.create_task(one(c, i)) for i, c in enumerate(components)
    ]
    for finished in asyncio.as_completed(tasks):
        result = await finished
        writer.write_row(result)
        emit(
            "row_written",
            slug=result.component.slug,
            from_cache=result.from_cache,
            failed=bool(result.error),
        )
        results.append(result)
    return results
