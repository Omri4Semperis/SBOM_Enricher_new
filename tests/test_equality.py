"""Equality ladder tests (judge mocked)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import equality
from download import DownloadResult
from equality import EqResult


def test_name_identical():
    r = asyncio.run(equality.compare_name("MIT", "MIT"))
    assert r == EqResult("TRUE", "identical")


def test_name_normalized_only():
    r = asyncio.run(equality.compare_name("mit", "MIT"))
    assert r == EqResult("TRUE", "normalized")


def test_name_judge_decides():
    client = AsyncMock()
    client.complete_json = AsyncMock(
        return_value={"verdict": "TRUE", "reasoning": "same SPDX family"}
    )
    r = asyncio.run(equality.compare_name("GPL-3.0", "GPL-3.0-only", client=client))
    assert r.verdict == "TRUE"
    assert r.reason.startswith("judge:")
    client.complete_json.assert_awaited_once()


def test_copyright_normalized():
    r = asyncio.run(
        equality.compare_copyright(
            "Copyright (c) 2020 Jane Doe",
            "Copyright © 2020 Jane Doe",
        )
    )
    assert r == EqResult("TRUE", "normalized")


def test_url_identical_bytes(tmp_path, monkeypatch):
    body = b"MIT License\nPermission is hereby granted.\n"

    async def fake_fetch(url, purl, dest_dir, slug):
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(body)
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(
            "https://example.com/a",
            "https://example.com/b",
            tmp_path,
            "pkg",
        )
    )
    assert r == EqResult("TRUE", "identical")


def test_url_normalized_whitespace(tmp_path, monkeypatch):
    bodies = {
        "https://a": b"MIT License\r\n\r\nFoo\n",
        "https://b": b"mit license\n\nfoo\n",
    }

    async def fake_fetch(url, purl, dest_dir, slug):
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(bodies[url])
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content("https://a", "https://b", tmp_path, "pkg")
    )
    assert r == EqResult("TRUE", "normalized")


def test_url_judge_decides(tmp_path, monkeypatch):
    bodies = {"https://a": b"AAA license text", "https://b": b"BBB other text"}

    async def fake_fetch(url, purl, dest_dir, slug):
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(bodies[url])
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    client = AsyncMock()
    client.complete_json = AsyncMock(
        return_value={"verdict": "FALSE", "reasoning": "different licenses"}
    )
    r = asyncio.run(
        equality.compare_url_content(
            "https://a", "https://b", tmp_path, "pkg", client=client
        )
    )
    assert r.verdict == "FALSE"
    assert "judge:" in r.reason


def test_gt_url_download_fail(tmp_path, monkeypatch):
    async def fake_fetch(url, purl, dest_dir, slug):
        if "gt" in url:
            return DownloadResult(error="download_failed", original_url=url)
        licenses = Path(dest_dir) / "licenses"
        licenses.mkdir(parents=True, exist_ok=True)
        path = licenses / f"{slug}.txt"
        path.write_bytes(b"ok")
        return DownloadResult(resolved_url=url, saved_path=path, original_url=url)

    monkeypatch.setattr(equality, "fetch_license_file", fake_fetch)
    r = asyncio.run(
        equality.compare_url_content(
            "https://inf.example/LICENSE",
            "https://gt.example/LICENSE",
            tmp_path,
            "pkg",
        )
    )
    assert r == EqResult("FALSE", "gt_url_download_failed")
