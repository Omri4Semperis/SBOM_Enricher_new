"""Per-component stub pipeline and bounded asyncio worker pool."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from config import Config
from input_csv import Component
from results_csv import ResultsWriter

STORY_FILENAME = "story.txt"


@dataclass
class ComponentResult:
    component: Component
    inferred_license_name: str = "UNKNOWN"
    inferred_license_code_url: str = "UNKNOWN"
    inferred_copyright: str = "UNKNOWN"


def story_path(run_dir: Path, slug: str) -> Path:
    return run_dir / "per_component" / slug / STORY_FILENAME


def append_story(run_dir: Path, slug: str, line: str) -> None:
    path = story_path(run_dir, slug)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip() + "\n")


async def process_component(comp: Component, run_dir: Path) -> ComponentResult:
    result = ComponentResult(component=comp)
    append_story(run_dir, comp.slug, "stub: no inference run")
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
            return await process_component(comp, run_dir)

    tasks = [asyncio.create_task(one(c)) for c in components]
    for finished in asyncio.as_completed(tasks):
        result = await finished
        writer.write_row(result)
        results.append(result)
    return results
