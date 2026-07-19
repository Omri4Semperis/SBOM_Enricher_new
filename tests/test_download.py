"""Pure helpers + fetch orchestration for license download."""

import asyncio
from unittest.mock import MagicMock

from download import (
    _write_license,
    fetch_license_file,
    is_generic_template,
    looks_like_html,
    npm_candidates,
    nuget_candidates,
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


_NUSPEC_WITH_REPO = b"""<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Newtonsoft.Json</id>
    <repository type="git" url="https://github.com/JamesNK/Newtonsoft.Json.git" />
    <license type="expression">MIT</license>
  </metadata>
</package>
"""

_NUSPEC_SPDX_ONLY = b"""<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Some.Package</id>
    <license type="expression">MIT</license>
  </metadata>
</package>
"""


def test_nuget_candidates_repo(monkeypatch):
    seen = []

    def fake_get(url, timeout=None):
        seen.append(url)
        return _ok_response(_NUSPEC_WITH_REPO, "application/xml")

    monkeypatch.setattr("download.requests.get", fake_get)

    urls = nuget_candidates("pkg:nuget/Newtonsoft.Json@13.0.3")
    assert (
        seen[0]
        == "https://api.nuget.org/v3-flatcontainer/newtonsoft.json/13.0.3/newtonsoft.json.nuspec"
    )
    assert urls[0] == "https://raw.githubusercontent.com/JamesNK/Newtonsoft.Json/HEAD/LICENSE"


def test_nuget_candidates_spdx_only_empty(monkeypatch):
    monkeypatch.setattr(
        "download.requests.get",
        lambda url, timeout=None: _ok_response(_NUSPEC_SPDX_ONLY, "application/xml"),
    )
    assert nuget_candidates("pkg:nuget/Some.Package@1.0.0") == []


def test_nuget_candidates_non_nuget():
    assert nuget_candidates("") == []
    assert nuget_candidates("pkg:npm/lodash@4.17.21") == []


_NUSPEC_NON_GITHUB_REPO = b"""<?xml version="1.0"?>
<package xmlns="http://schemas.microsoft.com/packaging/2013/05/nuspec.xsd">
  <metadata>
    <id>Some.Package</id>
    <repository type="git" url="https://gitlab.com/someowner/somerepo.git" />
    <license type="expression">MIT</license>
  </metadata>
</package>
"""


def test_nuget_candidates_non_github_repo_empty(monkeypatch):
    monkeypatch.setattr(
        "download.requests.get",
        lambda url, timeout=None: _ok_response(
            _NUSPEC_NON_GITHUB_REPO, "application/xml"
        ),
    )
    assert nuget_candidates("pkg:nuget/Some.Package@1.0.0") == []


def test_nuget_version_normalized(monkeypatch):
    seen = []

    def fake_get(url, timeout=None):
        seen.append(url)
        return _ok_response(_NUSPEC_WITH_REPO, "application/xml")

    monkeypatch.setattr("download.requests.get", fake_get)

    nuget_candidates("pkg:nuget/Some.Package@1.0.0.0")
    assert seen[-1].split("/")[-2] == "1.0.0"

    nuget_candidates("pkg:nuget/Some.Package@2.1.0-RC1")
    assert seen[-1].split("/")[-2] == "2.1.0-rc1"


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


def test_fetch_html_sets_fail_kind(tmp_path, monkeypatch):
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
    assert result.fail_kind == "html"


def test_fetch_http_error_fail_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "download.requests.get", lambda url, timeout=None: _status_response(404)
    )
    (tmp_path / "per_component" / "x@1").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file("https://example.com/gone", "", tmp_path, "x@1")
    )
    assert not result.ok
    assert result.fail_kind == "http_error"


def test_fetch_nuget_fallback_after_bad_claude(tmp_path, monkeypatch):
    claude = "https://example.com/missing"
    nuspec_url = (
        "https://api.nuget.org/v3-flatcontainer/"
        "newtonsoft.json/13.0.3/newtonsoft.json.nuspec"
    )
    raw_license = "https://raw.githubusercontent.com/JamesNK/Newtonsoft.Json/HEAD/LICENSE"

    def fake_get(url, timeout=None):
        if url == claude:
            return _status_response(404)
        if url == nuspec_url:
            return _ok_response(_NUSPEC_WITH_REPO, "application/xml")
        if url == raw_license:
            return _ok_response(b"MIT License\n")
        return _status_response(404)

    monkeypatch.setattr("download.requests.get", fake_get)
    (tmp_path / "per_component" / "newtonsoft.json@13.0.3").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file(
            claude, "pkg:nuget/Newtonsoft.Json@13.0.3", tmp_path, "newtonsoft.json@13.0.3"
        )
    )
    assert result.ok
    assert result.resolved_url == raw_license
    assert result.saved_path.read_bytes() == b"MIT License\n"


def test_fetch_nuget_offloaded_from_loop(tmp_path, monkeypatch):
    calls = []
    real_to_thread = asyncio.to_thread

    async def spying_to_thread(func, *args, **kwargs):
        calls.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr("download.asyncio.to_thread", spying_to_thread)
    monkeypatch.setattr(
        "download.requests.get",
        lambda url, timeout=None: _ok_response(_NUSPEC_WITH_REPO, "application/xml"),
    )
    (tmp_path / "per_component" / "newtonsoft.json@13.0.3").mkdir(parents=True)

    asyncio.run(
        fetch_license_file(
            "", "pkg:nuget/Newtonsoft.Json@13.0.3", tmp_path, "newtonsoft.json@13.0.3"
        )
    )
    assert nuget_candidates in calls, "nuget_candidates was not dispatched via asyncio.to_thread"


def test_fetch_nuget_purl_no_candidates_logs_lookup_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "download.requests.get", lambda url, timeout=None: _status_response(404)
    )
    (tmp_path / "per_component" / "some.package@1.0.0").mkdir(parents=True)

    result = asyncio.run(
        fetch_license_file(
            "", "pkg:nuget/Some.Package@1.0.0", tmp_path, "some.package@1.0.0"
        )
    )
    assert not result.ok
    assert any(
        "nuget: no candidates (nuspec/repo lookup failed)" in a for a in result.attempts
    )
    assert not any("non-nuget purl" in a for a in result.attempts)


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


def test_write_license_flat_default(tmp_path):
    body = b"MIT\n"
    path = _write_license(tmp_path, "pkg@1", ".txt", body)
    assert path == tmp_path / "licenses" / "pkg@1.txt"
    assert path.read_bytes() == body
    assert (tmp_path / "per_component" / "pkg@1" / "pkg@1.txt").read_bytes() == body


def test_write_license_per_project(tmp_path):
    body = b"MIT\n"
    path = _write_license(tmp_path, "pkg@1", ".txt", body, project_dirs=["a", "b"])
    assert path == tmp_path / "licenses" / "a" / "pkg@1.txt"
    assert (tmp_path / "licenses" / "a" / "pkg@1.txt").read_bytes() == body
    assert (tmp_path / "licenses" / "b" / "pkg@1.txt").read_bytes() == body
    assert (tmp_path / "per_component" / "pkg@1" / "pkg@1.txt").read_bytes() == body
    assert not (tmp_path / "licenses" / "pkg@1.txt").exists()


def test_write_license_dedups_project_dirs(tmp_path):
    body = b"MIT\n"
    path = _write_license(
        tmp_path, "pkg@1", ".txt", body, project_dirs=["a", "a", "b"]
    )
    assert path == tmp_path / "licenses" / "a" / "pkg@1.txt"
    assert (tmp_path / "licenses" / "a" / "pkg@1.txt").is_file()
    assert (tmp_path / "licenses" / "b" / "pkg@1.txt").is_file()
    # One file under a/ (not written twice as siblings).
    assert list((tmp_path / "licenses" / "a").iterdir()) == [
        tmp_path / "licenses" / "a" / "pkg@1.txt"
    ]
