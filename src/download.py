"""License-file download: viewer→raw rewrite, HTML reject, npm/unpkg fallback."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
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


def _normalize_nuget_version(version: str) -> str:
    """NuGet-normalize a version for the flat-container URL (lowercase, no
    build metadata, no leading zeros, no trailing zero 4th segment)."""
    value = unquote(version).strip().split("+", 1)[0].lower()
    numeric, sep, prerelease = value.partition("-")
    segments = [str(int(s)) if s.isdigit() else s for s in numeric.split(".")]
    if len(segments) == 4 and segments[3] == "0":
        segments = segments[:3]
    numeric = ".".join(segments)
    return numeric + sep + prerelease


def nuget_candidates(purl: str) -> list[str]:
    """Raw LICENSE candidate URLs from a pkg:nuget purl's nuspec <repository url>.

    Fail-closed: any network/parse issue, or a nuspec with only an SPDX
    expression or legacy licenseUrl (no <repository url>), returns []. Never
    fabricates a URL from an SPDX id.
    """
    cleaned = purl.strip()
    if not cleaned.lower().startswith("pkg:nuget/"):
        return []

    remainder = cleaned[len("pkg:nuget/") :]
    remainder = remainder.split("?", 1)[0].split("#", 1)[0]
    if "@" not in remainder:
        return []

    name_part, _, version = remainder.rpartition("@")
    package_id = unquote(name_part).strip()
    version = version.strip()
    if not package_id or not version:
        return []

    id_lower = package_id.lower()
    version_for_url = _normalize_nuget_version(version)
    nuspec_url = (
        f"https://api.nuget.org/v3-flatcontainer/{id_lower}/{version_for_url}/{id_lower}.nuspec"
    )
    try:
        response = requests.get(nuspec_url, timeout=FETCH_TIMEOUT_S)
    except Exception:
        return []
    if response.status_code != 200:
        return []

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return []

    repo_url = ""
    for elem in root.iter():
        if elem.tag.rsplit("}", 1)[-1] == "repository":
            repo_url = (elem.get("url") or "").strip()
            break
    if repo_url.endswith(".git"):
        repo_url = repo_url[: -len(".git")]
    split_repo = urlsplit(repo_url)
    if (split_repo.hostname or "").lower() not in {"github.com", "www.github.com"}:
        return []
    segments = [s for s in split_repo.path.split("/") if s]
    if len(segments) < 2:
        return []
    owner, repo = segments[0], segments[1]

    # ponytail: HEAD ref, pin to tag if version skew bites
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{filename}"
        for filename in NPM_LICENSE_FILENAMES
    ]


@dataclass
class DownloadResult:
    resolved_url: str = ""
    saved_path: Path | None = None
    error: str = ""
    original_url: str = ""
    attempts: list[str] = field(default_factory=list)
    fail_kind: str = ""

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


async def _try_one(
    url: str, dest_dir: Path, slug: str, attempts: list[str]
) -> tuple[Path | None, str]:
    """Fetch one URL; return (saved path, "") on success, else (None, fail_kind)."""
    rewritten = rewrite_viewer_to_raw(url)
    if rewritten != url:
        attempts.append(f"rewrite {url} -> {rewritten}")

    if is_generic_template(rewritten):
        attempts.append(f"reject template: {rewritten}")
        return None, "template"

    try:
        body, content_type = await with_retries(
            lambda: asyncio.to_thread(_get_bytes, rewritten),
            classify=_classify_http,
        )
    except Exception as exc:
        attempts.append(f"fail {rewritten}: {exc}")
        message = str(exc)
        kind = "network" if message.startswith(("network:", "timeout:")) else "http_error"
        return None, kind

    if looks_like_html(body, content_type):
        attempts.append(f"reject html: {rewritten}")
        return None, "html"

    ext = _ext_for(rewritten, content_type)
    path = _write_license(dest_dir, slug, ext, body)
    attempts.append(f"ok {rewritten} -> {path.name}")
    return path, ""


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
    fail_kind = ""

    if original:
        path, kind = await _try_one(original, dest_dir, slug, attempts)
        if kind:
            fail_kind = kind
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
        path, kind = await _try_one(candidate, dest_dir, slug, attempts)
        if kind:
            fail_kind = kind
        if path is not None:
            result.resolved_url = rewrite_viewer_to_raw(candidate)
            result.saved_path = path
            return result

    nuget_cands = await asyncio.to_thread(nuget_candidates, purl)
    if not (purl or "").strip():
        attempts.append("empty purl: skip nuget fallback")
    elif not nuget_cands:
        attempts.append("non-nuget purl: skip nuget fallback")

    for candidate in nuget_cands:
        path, kind = await _try_one(candidate, dest_dir, slug, attempts)
        if kind:
            fail_kind = kind
        if path is not None:
            result.resolved_url = rewrite_viewer_to_raw(candidate)
            result.saved_path = path
            return result

    result.error = "download_failed"
    result.fail_kind = fail_kind
    return result
