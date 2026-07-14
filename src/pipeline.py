"""Per-component pipeline and bounded asyncio worker pool."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from claude_client import infer_license
from config import Config
from copyright import extract_copyright
from download import fetch_license_file
from input_csv import Component
from results_csv import ResultsWriter

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


def story_path(run_dir: Path, slug: str) -> Path:
    return run_dir / "per_component" / slug / STORY_FILENAME


def append_story(run_dir: Path, slug: str, line: str) -> None:
    path = story_path(run_dir, slug)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


async def process_component(
    comp: Component, run_dir: Path, model: str
) -> ComponentResult:
    result = ComponentResult(component=comp)
    if not (comp.purl or "").strip():
        append_story(run_dir, comp.slug, "no purl")

    t0 = time.perf_counter()
    data = await infer_license(comp.purl, comp.lib_name, comp.version, model)
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

    if result.license_file_path is not None:
        text = result.license_file_path.read_text(encoding="utf-8", errors="replace")
        t2 = time.perf_counter()
        cr = await extract_copyright(text)
        cr_elapsed = time.perf_counter() - t2
        result.inferred_copyright = cr["copyright"]
        append_story(
            run_dir,
            comp.slug,
            f"copyright: {cr['reasoning']} timing_s={cr_elapsed:.3f}",
        )
    else:
        append_story(run_dir, comp.slug, "copyright: skipped (no license file)")
    return result


async def run_workers(
    config: Config,
    components: list[Component],
    run_dir: Path,
    writer: ResultsWriter,
) -> list[ComponentResult]:
    sem = asyncio.Semaphore(config.workers)
    results: list[ComponentResult] = []

    async def one(comp: Component) -> ComponentResult:
        async with sem:
            return await process_component(comp, run_dir, config.model)

    tasks = [asyncio.create_task(one(c)) for c in components]
    for finished in asyncio.as_completed(tasks):
        result = await finished
        writer.write_row(result)
        results.append(result)
    return results
