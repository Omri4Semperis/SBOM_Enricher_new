"""Equality ladder tests (judge mocked)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import equality
from download import DownloadResult
from equality import EqResult
from pricing import CallMeta


def _judge_meta(cost_usd: float = 0.002) -> CallMeta:
    meta = CallMeta()
    meta.add_call(cost_usd=cost_usd, raw='{"verdict":"TRUE"}')
    return meta


def _inferred(tmp_path: Path, body: bytes = b"MIT License\n") -> Path:
    path = tmp_path / "inferred.txt"
    path.write_bytes(body)
    return path


def test_name_identical():
    r = asyncio.run(equality.compare_name("MIT", "MIT"))
    assert r == EqResult("TRUE", "identical")
    assert r.meta.billable_calls == 0


def test_name_normalized_only():
    r = asyncio.run(equality.compare_name("mit", "MIT"))
    assert r == EqResult("TRUE", "normalized")
    assert r.meta.billable_calls == 0


def test_name_judge_decides():
    client = AsyncMock()
    client.complete_json = AsyncMock(
        return_value=(
            {"verdict": "TRUE", "reasoning": "same SPDX family"},
            _judge_meta(),
        )
    )
    r = asyncio.run(equality.compare_name("GPL-3.0", "GPL-3.0-only", client=client))
    assert r.verdict == "TRUE"
    assert r.reason.startswith("judge:")
    assert r.meta.billable_calls == 1
    assert r.meta.cost_cell() != "unknown"
    client.complete_json.assert_awaited_once()


def test_name_no_judge():
    r = asyncio.run(equality.compare_name("GPL-3.0", "MIT", client=None))
    assert r == EqResult("FALSE", "no_judge")
    assert r.meta.billable_calls == 0


def test_copyright_normalized():
    r = asyncio.run(
        equality.compare_copyright(
            "Copyright (c) 2020 Jane Doe",
            "Copyright © 2020 Jane Doe",
        )
    )
    assert r == EqResult("TRUE", "normalized")
    assert r.meta.billable_calls == 0


def test_url_identical_bytes(tmp_path, monkeypatch):
    body = b"MIT License\nPermission is hereby granted.\n"
    inf = _inferred(tmp_path, body)
    calls: list[str] = []

    async def fake_fetch(url, purl, dest_dir, slug, project_dirs=None):
        calls.append(slug)
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(body)
        per = Path(dest_dir) / "per_component" / slug
        per.mkdir(parents=True, exist_ok=True)
        (per / path.name).write_bytes(body)
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(inf, "https://example.com/b", tmp_path, "pkg")
    )
    assert r == EqResult("TRUE", "identical")
    assert r.meta.billable_calls == 0
    assert calls == ["pkg__eq_gt"]
    assert not (tmp_path / "licenses" / "pkg__eq_gt.txt").exists()
    assert (tmp_path / "per_component" / "pkg__eq_gt" / "pkg__eq_gt.txt").is_file()
    assert inf.is_file()


def test_url_normalized_whitespace(tmp_path, monkeypatch):
    inf = _inferred(tmp_path, b"MIT License\r\n\r\nFoo\n")

    async def fake_fetch(url, purl, dest_dir, slug, project_dirs=None):
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(b"mit license\n\nfoo\n")
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(inf, "https://b", tmp_path, "pkg")
    )
    assert r == EqResult("TRUE", "normalized")
    assert r.meta.billable_calls == 0
    assert not (tmp_path / "licenses" / "pkg__eq_gt.txt").exists()


def test_url_judge_decides(tmp_path, monkeypatch):
    inf = _inferred(tmp_path, b"AAA license text")

    async def fake_fetch(url, purl, dest_dir, slug, project_dirs=None):
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(b"BBB other text")
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    client = AsyncMock()
    client.complete_json = AsyncMock(
        return_value=(
            {"verdict": "FALSE", "reasoning": "different licenses"},
            _judge_meta(0.003),
        )
    )
    r = asyncio.run(
        equality.compare_url_content(
            inf, "https://b", tmp_path, "pkg", client=client
        )
    )
    assert r.verdict == "FALSE"
    assert "judge:" in r.reason
    assert r.meta.billable_calls == 1
    assert not (tmp_path / "licenses" / "pkg__eq_gt.txt").exists()


def test_inferred_file_missing_skips_gt(tmp_path, monkeypatch):
    called = False

    async def fake_fetch(*_a, **_k):
        nonlocal called
        called = True
        raise AssertionError("must not fetch GT when inferred missing")

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(None, "https://gt.example/LICENSE", tmp_path, "pkg")
    )
    assert r == EqResult("FALSE", "inferred_file_missing")
    assert not called

    missing = tmp_path / "gone.txt"
    r2 = asyncio.run(
        equality.compare_url_content(missing, "https://gt.example/LICENSE", tmp_path, "pkg")
    )
    assert r2 == EqResult("FALSE", "inferred_file_missing")
    assert not called


def test_gt_html_landing_page_unscoreable(tmp_path, monkeypatch):
    inf = _inferred(tmp_path, b"ok")

    async def fake_fetch(url, purl, dest_dir, slug, project_dirs=None):
        return DownloadResult(
            error="download_failed", original_url=url, fail_kind="html"
        )

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(
            inf,
            "https://gt.example/LICENSE",
            tmp_path,
            "pkg",
        )
    )
    assert r.verdict == "UNSCOREABLE"
    assert r.reason == "gt_not_a_file"
    assert r.meta.billable_calls == 0


def test_gt_url_download_fail(tmp_path, monkeypatch):
    inf = _inferred(tmp_path, b"ok")

    async def fake_fetch(url, purl, dest_dir, slug, project_dirs=None):
        return DownloadResult(error="download_failed", original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(
            inf,
            "https://gt.example/LICENSE",
            tmp_path,
            "pkg",
        )
    )
    assert r == EqResult("FALSE", "gt_url_download_failed")
    assert r.meta.billable_calls == 0
