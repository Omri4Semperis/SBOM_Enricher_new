"""Pure helpers + fetch orchestration for license download."""

from download import (
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
