import asyncio
import csv
from pathlib import Path
from unittest.mock import AsyncMock

import config
import main
import pipeline
import run_dir
from download import DownloadResult

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini.csv"
AUDIT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_audit.csv"


async def _fake_infer(purl, lib_name, version, model):
    return {
        "license_name": "MIT",
        "license_code_url": "https://github.com/foo/bar/blob/main/LICENSE",
        "reasoning": "mocked sources ok",
        "attempts": 1,
    }


async def _fake_download(claude_url, purl, dest_dir, slug, project_dirs=None):
    raw = "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    licenses = dest_dir / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    path = licenses / f"{slug}.txt"
    path.write_bytes(b"MIT License\n")
    per = dest_dir / "per_component" / slug
    per.mkdir(parents=True, exist_ok=True)
    (per / path.name).write_bytes(b"MIT License\n")
    return DownloadResult(
        resolved_url=raw,
        saved_path=path,
        original_url=claude_url,
        attempts=[f"rewrite {claude_url} -> {raw}", f"ok {raw} -> {path.name}"],
    )


async def _fake_copyright(_client, license_text, purl="", lib_name="", version="", model=""):
    return {
        "copyright": "Copyright (c) 2020 Jane Doe",
        "reasoning": "verbatim notice",
    }


def test_mocked_license_lands_in_results_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)

    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=2,
        cache_read=None,
        cache_write=None,
    )
    out = main.run(cfg)
    results_path = out / run_dir.results_csv_name(cfg.model, 3)
    assert results_path.is_file()
    with results_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert list(rows[0].keys())[:5] == [
        "component_name",
        "purl",
        "inferred_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
    ]
    assert "notes" in rows[0]
    resolved = "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    for row in rows:
        assert row["inferred_license_name"] == "MIT"
        assert row["inferred_license_code_url"] == resolved
        assert row["inferred_copyright"] == "Copyright (c) 2020 Jane Doe"
        slug = row["component_name"]
        story = (out / "per_component" / slug / pipeline.STORY_FILENAME).read_text(
            encoding="utf-8"
        )
        assert "mocked sources ok" in story
        assert "attempts=1" in story
        assert "timing_s=" in story
        assert "download: chose " + resolved in story
        assert "copyright: verbatim notice" in story
        assert (out / "licenses" / f"{slug}.txt").is_file()


def test_process_records_license_file_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)

    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(
        pipeline.process_component(comp, run, "claude-haiku-4-5", AsyncMock())
    )
    assert result.inferred_license_code_url == (
        "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    )
    assert result.license_file_path == run / "licenses" / "solo@1.0.txt"
    assert result.license_file_path.is_file()
    assert result.download_attempts
    assert result.original_license_url.endswith("/blob/main/LICENSE")
    assert result.inferred_copyright == "Copyright (c) 2020 Jane Doe"


def test_empty_purl_noted_in_story(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)

    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(
        pipeline.process_component(comp, run, "claude-haiku-4-5", AsyncMock())
    )
    assert result.inferred_license_name == "MIT"
    story = (run / "per_component" / comp.slug / pipeline.STORY_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "no purl" in story
    assert "mocked sources ok" in story
    assert "download: chose" in story


def test_no_file_still_resolves_copyright(tmp_path, monkeypatch):
    async def fail_download(claude_url, purl, dest_dir, slug, project_dirs=None):
        return DownloadResult(
            resolved_url="",
            saved_path=None,
            error="all candidates failed",
            original_url=claude_url,
            attempts=["fail https://example.com"],
        )

    async def fake_resolve(_client, license_text, purl, lib_name, version, model):
        assert license_text == ""
        return {"copyright": "UNKNOWN", "reasoning": "empty license text"}

    resolve = AsyncMock(side_effect=fake_resolve)
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", fail_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", resolve)

    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(
        pipeline.process_component(comp, run, "claude-haiku-4-5", AsyncMock())
    )
    assert result.inferred_copyright == "UNKNOWN"
    assert result.license_file_path is None
    resolve.assert_awaited_once()
    story = (run / "per_component" / comp.slug / pipeline.STORY_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "copyright: empty license text" in story


def test_cache_hit_skips_stages(tmp_path, monkeypatch):
    from cache import write_cache
    from input_csv import Component

    seed_lic = tmp_path / "seed.txt"
    seed_lic.write_bytes(b"cached license body\n")
    seed = pipeline.ComponentResult(
        component=Component(
            component_name="solo@1.0",
            purl="pkg:npm/solo@1.0",
            lib_name="solo",
            version="1.0",
            slug="solo@1.0",
            extras={},
        ),
        inferred_license_name="Apache-2.0",
        inferred_license_code_url="https://example.com/LICENSE",
        inferred_copyright="Copyright (c) Cached",
        license_file_path=seed_lic,
    )
    cache_dir = tmp_path / "cache"
    assert write_cache(cache_dir, "solo@1.0", seed)

    infer = AsyncMock(side_effect=AssertionError("infer must not run"))
    download = AsyncMock(side_effect=AssertionError("download must not run"))
    extract = AsyncMock(side_effect=AssertionError("copyright must not run"))
    monkeypatch.setattr(pipeline, "infer_license", infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", download)
    monkeypatch.setattr(pipeline, "resolve_copyright", extract)

    comp = seed.component
    run = tmp_path / "run"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(
        pipeline.process_component(
            comp, run, "claude-haiku-4-5", AsyncMock(), cache_read=cache_dir
        )
    )
    assert result.from_cache is True
    assert result.inferred_license_name == "Apache-2.0"
    assert result.inferred_copyright == "Copyright (c) Cached"
    assert result.license_file_path == run / "licenses" / "solo@1.0.txt"
    assert result.license_file_path.read_bytes() == b"cached license body\n"
    assert (run / "per_component" / "solo@1.0" / "solo@1.0.txt").is_file()
    infer.assert_not_awaited()
    download.assert_not_awaited()
    extract.assert_not_awaited()
    story = (run / "per_component" / comp.slug / pipeline.STORY_FILENAME).read_text(
        encoding="utf-8"
    )
    assert "cache hit" in story


def test_cache_write_on_full_success(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)

    from cache import read_cache
    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    cache_dir = tmp_path / "cache"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    result = asyncio.run(
        pipeline.process_component(
            comp, run, "claude-haiku-4-5", AsyncMock(), cache_write=cache_dir
        )
    )
    assert result.from_cache is False
    got = read_cache(cache_dir, "solo@1.0")
    assert got is not None
    assert got.inferred_license_name == "MIT"
    assert got.inferred_copyright == "Copyright (c) 2020 Jane Doe"


def test_cache_write_skips_unknown_copyright(tmp_path, monkeypatch):
    async def unknown_copyright(
        _client, license_text, purl="", lib_name="", version="", model=""
    ):
        return {"copyright": "UNKNOWN", "reasoning": "none found"}

    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", unknown_copyright)

    from cache import read_cache
    from input_csv import Component

    comp = Component(
        component_name="solo@1.0",
        purl="pkg:npm/solo@1.0",
        lib_name="solo",
        version="1.0",
        slug="solo@1.0",
        extras={},
    )
    run = tmp_path / "run"
    cache_dir = tmp_path / "cache"
    (run / "per_component" / comp.slug).mkdir(parents=True)

    asyncio.run(
        pipeline.process_component(
            comp, run, "claude-haiku-4-5", AsyncMock(), cache_write=cache_dir
        )
    )
    assert read_cache(cache_dir, "solo@1.0") is None
    assert not (cache_dir / "cache.csv").exists()


def test_audit_fixture_triplets_and_score(tmp_path, monkeypatch):
    import equality

    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)
    monkeypatch.setattr(equality, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "Gpt41Client", lambda: AsyncMock())

    cfg = config.Config(
        input_file_path=AUDIT_FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=1,
        cache_read=None,
        cache_write=None,
    )
    out = main.run(cfg)
    results_path = out / run_dir.results_csv_name(cfg.model, 1)
    with results_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys())[:11] == [
        "component_name",
        "purl",
        "license_name",
        "inferred_license_name",
        "is_eq_license_name",
        "license_code_url",
        "inferred_license_code_url",
        "is_eq_license_code_url",
        "copyright",
        "inferred_copyright",
        "is_eq_copyright",
    ]
    assert rows[0]["is_eq_license_name"] == "TRUE"
    assert rows[0]["is_eq_copyright"] == "TRUE"
    assert rows[0]["is_eq_license_code_url"] == "TRUE"
    score_path = out / "score.csv"
    assert score_path.is_file()
    with score_path.open(newline="", encoding="utf-8-sig") as f:
        score_rows = list(csv.DictReader(f))
    assert score_rows
    assert score_rows[0]["Count"] == "1"
    assert score_rows[0]["license_name"] == "Hit"


def test_non_gt_fixture_no_is_eq_no_score(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", _fake_copyright)

    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=2,
        cache_read=None,
        cache_write=None,
    )
    out = main.run(cfg)
    results_path = out / run_dir.results_csv_name(cfg.model, 3)
    with results_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    keys = list(rows[0].keys())
    assert keys == [
        "component_name",
        "purl",
        "inferred_license_name",
        "inferred_license_code_url",
        "inferred_copyright",
        "notes",
    ]
    assert not (out / "score.csv").exists()


def test_non_audit_run_shares_one_gpt_client(tmp_path, monkeypatch):
    client = object()
    factory_calls = 0
    received_clients = []

    def make_client():
        nonlocal factory_calls
        factory_calls += 1
        return client

    async def fake_copyright(
        received_client, license_text, purl="", lib_name="", version="", model=""
    ):
        received_clients.append(received_client)
        return {
            "copyright": "Copyright (c) 2020 Jane Doe",
            "reasoning": "verbatim notice",
        }

    monkeypatch.setattr(pipeline, "Gpt41Client", make_client)
    monkeypatch.setattr(pipeline, "infer_license", _fake_infer)
    monkeypatch.setattr(pipeline, "fetch_license_file", _fake_download)
    monkeypatch.setattr(pipeline, "resolve_copyright", fake_copyright)
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=2,
        cache_read=None,
        cache_write=None,
    )

    main.run(cfg)

    assert factory_calls == 1
    assert received_clients == [client, client, client]


def test_worker_failure_writes_failed_result_and_releases_slot(tmp_path, monkeypatch):
    from input_csv import Component

    class Writer:
        def __init__(self):
            self.rows = []

        def write_row(self, result):
            self.rows.append(result)

    async def fake_process(comp, *_args, **_kwargs):
        if comp.slug == "bad":
            raise RuntimeError("provider unavailable")
        return pipeline.ComponentResult(component=comp, inferred_license_name="MIT")

    components = [
        Component(
            component_name=slug,
            purl=f"pkg:npm/{slug}",
            lib_name=slug,
            version="1.0",
            slug=slug,
            extras={},
        )
        for slug in ("bad", "good-1", "good-2")
    ]
    run = tmp_path / "run"
    for component in components:
        (run / "per_component" / component.slug).mkdir(parents=True)
    monkeypatch.setattr(pipeline, "Gpt41Client", object)
    monkeypatch.setattr(pipeline, "process_component", fake_process)
    cfg = config.Config(
        input_file_path=FIXTURE,
        output_base_path=tmp_path / "runs",
        run_name=None,
        model="claude-opus-4-8",
        workers=1,
        cache_read=None,
        cache_write=None,
    )
    writer = Writer()

    results = asyncio.run(pipeline.run_workers(cfg, components, run, writer))

    assert len(results) == len(components)
    assert len(writer.rows) == len(components)
    failed = next(result for result in results if result.component.slug == "bad")
    assert failed.error == "RuntimeError: provider unavailable"
    assert [result.component.slug for result in results if not result.error] == [
        "good-1",
        "good-2",
    ]
    assert "error: RuntimeError: provider unavailable" in (
        run / "per_component" / "bad" / pipeline.STORY_FILENAME
    ).read_text(encoding="utf-8")
