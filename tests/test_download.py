"""Pure helpers + fetch orchestration for license download."""

import asyncio
from unittest.mock import MagicMock

from download import (
    fetch_license_file,
    is_generic_template,
    looks_like_html,
    npm_candidates,
    rewrite_viewer_to_raw,
)


def test_rewrite_github_blob_to_raw():
    url = "https://github.com/foo/bar/blob/main/LICENSE"
    assert (
        rewrite_viewer_to_raw(url)
        == "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    )


def test_rewrite_gitlab_blob_to_raw():
    url = "https://gitlab.com/foo/bar/-/blob/main/LICENSE.md"
    assert (
        rewrite_viewer_to_raw(url)
        == "https://gitlab.com/foo/bar/-/raw/main/LICENSE.md"
    )


def test_rewrite_leaves_raw_unchanged():
    url = "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    assert rewrite_viewer_to_raw(url) == url


def test_html_reject_by_doctype():
    assert looks_like_html(b"<!DOCTYPE html><html><body>x</body></html>", "")


def test_html_reject_by_content_type():
    assert looks_like_html(b"MIT License", "text/html; charset=utf-8")


def test_html_accepts_plain_license():
    assert not looks_like_html(b"MIT License\n\nCopyright (c) 2020", "text/plain")


def test_generic_template_hosts():
    assert is_generic_template("https://opensource.org/licenses/MIT")
    assert is_generic_template("https://choosealicense.com/licenses/mit/")
    assert not is_generic_template("https://raw.githubusercontent.com/x/y/main/LICENSE")


def test_candidates_npm_ordering():
    urls = npm_candidates("pkg:npm/lodash@4.17.21")
    assert urls[0] == "https://unpkg.com/lodash@4.17.21/LICENSE"
    assert urls[1] == "https://unpkg.com/lodash@4.17.21/LICENSE.md"
    assert "https://unpkg.com/lodash@4.17.21/COPYING" in urls


def test_candidates_scoped_npm():
    urls = npm_candidates("pkg:npm/%40babel/types@7.29.7")
    assert urls[0] == "https://unpkg.com/@babel/types@7.29.7/LICENSE"


def test_candidates_empty_or_non_npm():
    assert npm_candidates("") == []
    assert npm_candidates("pkg:pypi/requests@2.0") == []


def _ok_response(body: bytes = b"MIT License\n", content_type: str = "text/plain"):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = body
    resp.headers = {"Content-Type": content_type}
    return resp


def _status_response(status: int):
    resp = MagicMock()
    resp.status_code = status
    resp.content = b""
    resp.headers = {}
    return resp


def test_fetch_blob_rewritten_and_saved(tmp_path, monkeypatch):
    blob = "https://github.com/foo/bar/blob/main/LICENSE"
    raw = "https://raw.githubusercontent.com/foo/bar/main/LICENSE"
    seen: list[str] = []

    def fake_get(url, timeout=None):
        seen.append(url)
        assert url == raw
        return _ok_response()

    monkeypatch.setattr("download.requests.get", fake_get)
    (tmp_path / "per_component" / "foo@1").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file(blob, "pkg:npm/foo@1", tmp_path, "foo@1")
    )
    assert result.ok
    assert result.resolved_url == raw
    assert result.saved_path == tmp_path / "licenses" / "foo@1.txt"
    assert result.saved_path.read_bytes() == b"MIT License\n"
    copy = tmp_path / "per_component" / "foo@1" / "foo@1.txt"
    assert copy.is_file()
    assert copy.read_bytes() == b"MIT License\n"
    assert seen == [raw]


def test_fetch_npm_fallback_after_bad_claude(tmp_path, monkeypatch):
    claude = "https://example.com/missing"
    unpkg = "https://unpkg.com/lodash@4.17.21/LICENSE"

    def fake_get(url, timeout=None):
        if url == claude:
            return _status_response(404)
        if url == unpkg:
            return _ok_response(b"lodash MIT\n")
        return _status_response(404)

    monkeypatch.setattr("download.requests.get", fake_get)
    (tmp_path / "per_component" / "lodash@4.17.21").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file(claude, "pkg:npm/lodash@4.17.21", tmp_path, "lodash@4.17.21")
    )
    assert result.ok
    assert result.resolved_url == unpkg
    assert result.saved_path.read_bytes() == b"lodash MIT\n"
    assert any("fail" in a and claude in a for a in result.attempts)
    assert any("ok " + unpkg in a for a in result.attempts)


def test_fetch_all_fail_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "download.requests.get", lambda url, timeout=None: _status_response(404)
    )
    (tmp_path / "per_component" / "x@1").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file(
            "https://example.com/gone", "pkg:npm/x@1", tmp_path, "x@1"
        )
    )
    assert not result.ok
    assert result.error == "download_failed"
    assert result.saved_path is None
    licenses = tmp_path / "licenses"
    assert not licenses.exists() or not any(licenses.iterdir())


def test_fetch_rejects_html_before_write(tmp_path, monkeypatch):
    def fake_get(url, timeout=None):
        return _ok_response(
            b"<!DOCTYPE html><html></html>", "text/html; charset=utf-8"
        )

    monkeypatch.setattr("download.requests.get", fake_get)
    (tmp_path / "per_component" / "x@1").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file("https://example.com/page", "", tmp_path, "x@1")
    )
    assert not result.ok
    assert any("reject html" in a for a in result.attempts)
    licenses = tmp_path / "licenses"
    assert not licenses.exists() or not any(licenses.iterdir())


def test_fetch_empty_purl_skips_npm(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "download.requests.get", lambda url, timeout=None: _status_response(404)
    )
    (tmp_path / "per_component" / "solo@1").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file("https://example.com/gone", "", tmp_path, "solo@1")
    )
    assert not result.ok
    assert any("empty purl" in a for a in result.attempts)
    assert not any("unpkg.com" in a for a in result.attempts)


def test_fetch_rejects_generic_template(tmp_path, monkeypatch):
    called = []

    def fake_get(url, timeout=None):
        called.append(url)
        return _ok_response()

    monkeypatch.setattr("download.requests.get", fake_get)
    (tmp_path / "per_component" / "x@1").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file(
            "https://opensource.org/licenses/MIT", "", tmp_path, "x@1"
        )
    )
    assert not result.ok
    assert called == []
    assert any("reject template" in a for a in result.attempts)
