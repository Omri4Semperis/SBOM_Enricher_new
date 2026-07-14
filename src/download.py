"""License-file download: viewer→raw rewrite, HTML reject, npm/unpkg fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

from retry import with_retries

FETCH_TIMEOUT_S = 30.0
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

GENERIC_LICENSE_HOSTS: frozenset[str] = frozenset({
    "opensource.org",
    "www.opensource.org",
    "spdx.org",
    "www.spdx.org",
    "choosealicense.com",
    "www.choosealicense.com",
    "licenses.nuget.org",
    "tldrlegal.com",
    "www.tldrlegal.com",
})

NPM_LICENSE_FILENAMES: tuple[str, ...] = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "license",
    "license.md",
    "license.txt",
    "LICENCE",
    "LICENCE.md",
    "COPYING",
    "COPYING.md",
    "COPYING.txt",
    "NOTICE",
    "NOTICE.md",
)


def rewrite_viewer_to_raw(url: str) -> str:
    """Rewrite GitHub/GitLab viewer URLs to raw-content equivalents."""
    split = urlsplit(url)
    host = (split.hostname or "").lower()
    path = split.path

    if host in {"github.com", "www.github.com"}:
        parts = path.split("/")
        if len(parts) >= 6 and parts[3] == "blob":
            owner, repo, ref = parts[1], parts[2], parts[4]
            file_path = "/".join(parts[5:])
            new_path = f"/{owner}/{repo}/{ref}/{file_path}"
            return urlunsplit(
                ("https", "raw.githubusercontent.com", new_path, split.query, split.fragment)
            )
        return url

    if host in {"gitlab.com", "www.gitlab.com"}:
        marker = "/-/blob/"
        if marker in path:
            prefix, _, rest = path.partition(marker)
            new_path = f"{prefix}/-/raw/{rest}"
            return urlunsplit(("https", host, new_path, split.query, split.fragment))
        return url

    return url


def looks_like_html(body: bytes, content_type: str = "") -> bool:
    """True if Content-Type is HTML or body opens with an HTML document signature."""
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime == "text/html":
        return True
    prefix = body[:2048].decode("utf-8", errors="ignore").lstrip("\ufeff \t\r\n")
    lowered = prefix.lower()
    return lowered.startswith("<!doctype html") or lowered.startswith("<html")


def is_generic_template(url: str) -> bool:
    """True if URL points at a generic license-template host (not package source)."""
    host = (urlsplit(url.strip()).hostname or "").lower()
    return host in GENERIC_LICENSE_HOSTS


def npm_candidates(purl: str) -> list[str]:
    """Ordered unpkg LICENSE candidate URLs from a pkg:npm purl; empty if not npm."""
    cleaned = purl.strip()
    if not cleaned.lower().startswith("pkg:npm/"):
        return []

    remainder = cleaned[len("pkg:npm/") :]
    remainder = remainder.split("?", 1)[0].split("#", 1)[0]
    if "@" not in remainder:
        return []

    name_part, _, version = remainder.rpartition("@")
    package_name = unquote(name_part).strip()
    version = version.strip()
    if not package_name or not version:
        return []

    return [
        f"https://unpkg.com/{package_name}@{version}/{filename}"
        for filename in NPM_LICENSE_FILENAMES
    ]


@dataclass
class DownloadResult:
    resolved_url: str = ""
    saved_path: Path | None = None
    error: str = ""
    original_url: str = ""
    attempts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.saved_path is not None


class _HttpFail(Exception):
    """Raised from a single GET so with_retries can classify it."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # "transient" | "hard"


def _classify_http(exc: BaseException) -> str:
    if isinstance(exc, _HttpFail):
        return exc.kind
    return "hard"


def _get_bytes(url: str) -> tuple[bytes, str]:
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT_S)
    except requests.Timeout as exc:
        raise _HttpFail("transient", f"timeout:{exc}") from exc
    except requests.RequestException as exc:
        raise _HttpFail("transient", f"network:{exc.__class__.__name__}") from exc

    status = response.status_code
    if status != 200:
        kind = "transient" if status in _RETRYABLE_STATUS else "hard"
        raise _HttpFail(kind, f"http_{status}")

    body = response.content
    if not body:
        raise _HttpFail("hard", "empty_body")
    return body, response.headers.get("Content-Type", "").strip()


def _ext_for(url: str, content_type: str) -> str:
    ext = Path(urlsplit(url).path).suffix.lower()
    if ext:
        return ext
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime in {"text/markdown", "text/x-markdown"}:
        return ".md"
    return ".txt"


def _write_license(dest_dir: Path, slug: str, ext: str, body: bytes) -> Path:
    licenses_dir = dest_dir / "licenses"
    licenses_dir.mkdir(parents=True, exist_ok=True)
    flat = licenses_dir / f"{slug}{ext}"
    flat.write_bytes(body)

    per = dest_dir / "per_component" / slug
    per.mkdir(parents=True, exist_ok=True)
    (per / flat.name).write_bytes(body)
    return flat


async def _try_one(url: str, dest_dir: Path, slug: str, attempts: list[str]) -> Path | None:
    """Fetch one URL; return saved path on success, None if this candidate is done."""
    rewritten = rewrite_viewer_to_raw(url)
    if rewritten != url:
        attempts.append(f"rewrite {url} -> {rewritten}")

    if is_generic_template(rewritten):
        attempts.append(f"reject template: {rewritten}")
        return None

    try:
        body, content_type = await with_retries(
            lambda: asyncio.to_thread(_get_bytes, rewritten),
            classify=_classify_http,
        )
    except Exception as exc:
        attempts.append(f"fail {rewritten}: {exc}")
        return None

    if looks_like_html(body, content_type):
        attempts.append(f"reject html: {rewritten}")
        return None

    ext = _ext_for(rewritten, content_type)
    path = _write_license(dest_dir, slug, ext, body)
    attempts.append(f"ok {rewritten} -> {path.name}")
    return path


async def fetch_license_file(
    claude_url: str,
    purl: str,
    dest_dir: Path,
    slug: str,
) -> DownloadResult:
    """Download LICENSE from Claude URL (rewritten) or npm/unpkg fallbacks.

    On success: resolved_url is the URL that worked, saved_path is licenses/{slug}.ext.
    On failure: error set, saved_path None. Attempts always recorded.
    """
    original = (claude_url or "").strip()
    result = DownloadResult(original_url=original)
    attempts = result.attempts

    if original:
        path = await _try_one(original, dest_dir, slug, attempts)
        if path is not None:
            # Last attempt line names the rewritten URL; recover it.
            resolved = rewrite_viewer_to_raw(original)
            result.resolved_url = resolved
            result.saved_path = path
            return result
    else:
        attempts.append("no claude url")

    candidates = npm_candidates(purl)
    if not (purl or "").strip():
        attempts.append("empty purl: skip npm fallback")
    elif not candidates:
        attempts.append("non-npm purl: skip npm fallback")

    for candidate in candidates:
        path = await _try_one(candidate, dest_dir, slug, attempts)
        if path is not None:
            result.resolved_url = rewrite_viewer_to_raw(candidate)
            result.saved_path = path
            return result

    result.error = "download_failed"
    return result
