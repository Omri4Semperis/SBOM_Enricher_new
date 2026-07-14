from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlsplit, urlunsplit

import requests

import config


FETCH_SOURCE_DOWNLOADED = "downloaded"
FETCH_SOURCE_MISSING = "missing"
FETCH_ERROR_GENERIC_LICENSE_PAGE = "generic_license_page"
FETCH_ERROR_HTML_PAGE = "html_page"

# HTTP statuses worth retrying: rate limiting and transient server errors.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

_NPM_REGISTRY_HOST = "https://registry.npmjs.org"


def license_filename(slug: str, ext: str) -> str:
    return f"{slug}_license{ext}"


@dataclass(frozen=True)
class LicenseFetchResult:
    source: str
    path: str
    ext: str
    error: str
    content_type: str
    bytes_written: int
    original_url: str = ""
    resolved_url: str = ""

    @classmethod
    def missing(
        cls,
        error: str,
        *,
        content_type: str = "",
        ext: str = "",
        original_url: str = "",
    ) -> "LicenseFetchResult":
        return cls(
            source=FETCH_SOURCE_MISSING,
            path="",
            ext=ext,
            error=error,
            content_type=content_type,
            bytes_written=0,
            original_url=original_url,
            resolved_url="",
        )

    def csv_fields(self) -> dict[str, str]:
        return {
            "license_file_source": self.source,
            "license_file_path": self.path,
            "license_file_ext": self.ext,
            "license_file_error": self.error,
            "license_file_original_url": self.original_url,
            "license_file_resolved_url": self.resolved_url,
        }

    def cache_fields(self) -> dict[str, str]:
        payload = self.csv_fields()
        payload["license_file_content_type"] = self.content_type
        payload["license_file_bytes"] = str(self.bytes_written)
        return payload

    def json_block(self) -> dict[str, str | int]:
        return {
            "source": self.source,
            "path": self.path,
            "ext": self.ext,
            "content_type": self.content_type,
            "bytes": self.bytes_written,
            "error": self.error,
            "original_url": self.original_url,
            "resolved_url": self.resolved_url,
        }


def _download(url: str, timeout_s: float) -> tuple[bytes, str]:
    for attempt in range(1, config.FETCH_MAX_ATTEMPTS + 1):
        is_last_attempt = attempt == config.FETCH_MAX_ATTEMPTS
        try:
            response = requests.get(url, timeout=timeout_s)
        except requests.RequestException as exc:
            if is_last_attempt:
                raise ValueError(f"network:{exc.__class__.__name__}") from exc
            time.sleep(config.FETCH_BACKOFF_BASE_S * attempt)
            continue

        if response.status_code != 200:
            if response.status_code in _RETRYABLE_STATUS and not is_last_attempt:
                time.sleep(config.FETCH_BACKOFF_BASE_S * attempt)
                continue
            raise ValueError(f"http_{response.status_code}")

        body = response.content
        if not body:
            raise ValueError("empty_body")

        return body, response.headers.get("Content-Type", "").strip()

    # The final attempt always returns or raises above; this satisfies the
    # type checker for the theoretically-unreachable fall-through.
    raise ValueError("network:RequestException")


def _decode_extensionless_text(body: bytes, content_type: str) -> tuple[str, str]:
    mime_type = content_type.split(";", 1)[0].strip().lower()
    if not mime_type.startswith("text/"):
        raise ValueError("content_type_not_text")
    if b"\x00" in body:
        raise ValueError("binary_null_bytes")

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("not_utf8") from exc

    for char in text:
        if char in "\n\r\t":
            continue
        codepoint = ord(char)
        if codepoint < 32 or codepoint == 127:
            raise ValueError("control_chars")
    return text, content_type


def _write_bytes(path: Path, body: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    return len(body)


def _is_generic_license_template_url(url: str) -> bool:
    split = urlsplit(url.strip())
    host = (split.hostname or "").lower()
    return host in config.GENERIC_LICENSE_HOSTS


def _rewrite_viewer_url_to_raw(url: str) -> str:
    """Rewrite a GitHub/GitLab file-viewer URL to its raw-content equivalent.

    ``/blob/`` URLs render an HTML viewer page rather than serving the file
    itself, so a license fetched from one is actually GitHub/GitLab chrome,
    not license text. Both hosts publish a raw equivalent at a predictable
    path, so rewrite deterministically before ever downloading. URLs that
    don't match either pattern are returned unchanged.
    """
    split = urlsplit(url)
    host = (split.hostname or "").lower()
    path = split.path

    if host in {"github.com", "www.github.com"}:
        parts = path.split("/")
        if len(parts) >= 6 and parts[3] == "blob":
            owner, repo, ref = parts[1], parts[2], parts[4]
            file_path = "/".join(parts[5:])
            new_path = f"/{owner}/{repo}/{ref}/{file_path}"
            return urlunsplit(("https", "raw.githubusercontent.com", new_path, split.query, split.fragment))
        return url

    if host in {"gitlab.com", "www.gitlab.com"}:
        marker = "/-/blob/"
        if marker in path:
            prefix, _, rest = path.partition(marker)
            new_path = f"{prefix}/-/raw/{rest}"
            return urlunsplit(("https", host, new_path, split.query, split.fragment))
        return url

    return url


def _looks_like_html_document(body: bytes) -> bool:
    """Return True if ``body`` opens with an HTML document signature.

    Only inspects a short decoded prefix so a genuine license file that
    merely mentions HTML somewhere in its body is never mistaken for a
    rendered viewer page.
    """
    prefix = body[:2048].decode("utf-8", errors="ignore").lstrip("\ufeff \t\r\n")
    lowered = prefix.lower()
    return lowered.startswith("<!doctype html") or lowered.startswith("<html")


def _parse_npm_tarball_url(url: str) -> tuple[str, str] | None:
    split = urlsplit(url.strip())
    if (split.hostname or "").lower() != "registry.npmjs.org":
        return None
    if not split.path.endswith(".tgz") or "/-/" not in split.path:
        return None

    pkg_part, _, file_part = split.path.partition("/-/")
    package_name = pkg_part.strip("/")
    tarball_name = file_part[: -len(".tgz")]
    unscoped_name = package_name.rsplit("/", 1)[-1]
    prefix = f"{unscoped_name}-"
    if not package_name or not tarball_name.startswith(prefix):
        return None

    version = tarball_name[len(prefix):]
    if not version or not version[0].isdigit():
        return None
    return package_name, version


def _parse_npm_purl(purl: str) -> tuple[str, str] | None:
    """Return the npm package name and version from a ``pkg:npm`` purl.

    Accepts plain, scoped, and percent-encoded names (e.g.
    ``pkg:npm/%40babel/types@7.29.7``), ignores any ``?`` qualifiers, and
    returns ``None`` for non-npm ecosystems or malformed purls.
    """
    cleaned = purl.strip()
    if not cleaned.lower().startswith("pkg:npm/"):
        return None

    remainder = cleaned[len("pkg:npm/"):]
    # Drop qualifiers and subpath so only the name@version coordinate remains.
    remainder = remainder.split("?", 1)[0].split("#", 1)[0]
    if "@" not in remainder:
        return None

    # Split name/version from the right so scoped names (which contain no '@'
    # themselves once the leading %40/@ is decoded) stay intact.
    name_part, _, version = remainder.rpartition("@")
    package_name = unquote(name_part).strip()
    version = version.strip()
    if not package_name or not version:
        return None
    return package_name, version


def _iter_npm_license_candidate_urls(package_name: str, version: str) -> Iterable[str]:
    """Yield ordered unpkg raw-file URLs for an npm package's license files."""
    for filename in config.NPM_LICENSE_FILENAME_CANDIDATES:
        yield f"https://unpkg.com/{package_name}@{version}/{filename}"


def _get_npm_registry_metadata(url: str, timeout_s: float) -> dict | None:
    """GET one npm registry metadata URL with retry on transient failures.

    Retries network errors and 429/5xx up to ``config.NPM_AUTHOR_MAX_ATTEMPTS``
    with linear backoff, mirroring ``_download``'s resilience shape. A 404
    means "no such name/version" -- a normal, expected outcome (e.g. an
    unpublished version) -- and is not retried. Fails closed to None on any
    unrecoverable error so callers never raise into orchestration.
    """
    for attempt in range(1, config.NPM_AUTHOR_MAX_ATTEMPTS + 1):
        is_last_attempt = attempt == config.NPM_AUTHOR_MAX_ATTEMPTS
        try:
            response = requests.get(url, timeout=timeout_s)
        except requests.RequestException:
            if is_last_attempt:
                return None
            time.sleep(config.NPM_AUTHOR_BACKOFF_BASE_S * attempt)
            continue

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            if response.status_code in _RETRYABLE_STATUS and not is_last_attempt:
                time.sleep(config.NPM_AUTHOR_BACKOFF_BASE_S * attempt)
                continue
            return None

        try:
            metadata = response.json()
        except ValueError:
            return None
        return metadata if isinstance(metadata, dict) else None

    return None


def _extract_npm_author(metadata: dict) -> str | None:
    """Read a copyright holder from npm registry metadata.

    Priority order: ``author.name`` -> ``author`` string form (``"Name
    <email> (url)"``, name only) -> ``contributors[0].name`` ->
    ``maintainers[0].name``. Returns None when no field yields a usable name.
    """
    author = metadata.get("author")
    if isinstance(author, dict):
        name = str(author.get("name", "")).strip()
        if name:
            return name
    elif isinstance(author, str):
        name = author.split("<", 1)[0].split("(", 1)[0].strip()
        if name:
            return name

    for key in ("contributors", "maintainers"):
        people = metadata.get(key)
        if isinstance(people, list) and people:
            first = people[0]
            if isinstance(first, dict):
                name = str(first.get("name", "")).strip()
                if name:
                    return name
    return None


def fetch_npm_author(purl: str, *, timeout_s: float = config.FETCH_TIMEOUT_S) -> str | None:
    """Return a copyright holder from npm registry metadata, or None.

    Deterministic copyright fallback for when a package's LICENSE file itself
    has no holder (generic template, missing file, 404, etc.): npm's
    canonical holder lives in ``package.json``'s ``author`` field, mirrored
    to the registry. Returns None immediately for non-npm/malformed purls, or
    when the registry has nothing usable -- callers must fail closed.
    """
    parsed = _parse_npm_purl(purl)
    if parsed is None:
        return None
    package_name, version = parsed

    for url in (
        f"{_NPM_REGISTRY_HOST}/{package_name}/{version}",
        f"{_NPM_REGISTRY_HOST}/{package_name}/latest",
    ):
        metadata = _get_npm_registry_metadata(url, timeout_s)
        if metadata is None:
            continue
        author = _extract_npm_author(metadata)
        if author:
            return author
    return None


def _attempt_fetch(
    url: str,
    responses_dir: Path,
    slug: str,
    timeout_s: float,
    original_url: str,
) -> LicenseFetchResult:
    url = _rewrite_viewer_url_to_raw(url)

    if _is_generic_license_template_url(url):
        return LicenseFetchResult.missing(FETCH_ERROR_GENERIC_LICENSE_PAGE, original_url=original_url)

    split = urlsplit(url)
    ext = Path(split.path).suffix.lower()
    if ext and ext not in config.ALLOWED_LICENSE_EXTS:
        return LicenseFetchResult.missing(f"disallowed_extension:{ext}", ext=ext, original_url=original_url)

    try:
        body, content_type = _download(url, timeout_s)
    except ValueError as exc:
        return LicenseFetchResult.missing(str(exc), ext=ext, original_url=original_url)

    if ext != ".html" and _looks_like_html_document(body):
        return LicenseFetchResult.missing(
            FETCH_ERROR_HTML_PAGE, content_type=content_type, ext=ext, original_url=original_url
        )

    save_ext = ext
    if not save_ext:
        try:
            _decode_extensionless_text(body, content_type)
        except ValueError as exc:
            return LicenseFetchResult.missing(str(exc), content_type=content_type, original_url=original_url)
        save_ext = ".txt"

    rel_path = Path("licenses") / license_filename(slug, save_ext)
    abs_path = responses_dir.parent / rel_path
    bytes_written = _write_bytes(abs_path, body)
    return LicenseFetchResult(
        source=FETCH_SOURCE_DOWNLOADED,
        path=rel_path.as_posix(),
        ext=save_ext,
        error="",
        content_type=content_type,
        bytes_written=bytes_written,
        original_url=original_url,
        resolved_url=url,
    )


def fetch_license_file(
    license_url: str,
    responses_dir: Path,
    slug: str,
    *,
    purl: str = "",
    timeout_s: float = config.FETCH_TIMEOUT_S,
) -> LicenseFetchResult:
    original_url = license_url.strip()

    primary: LicenseFetchResult | None = None
    if original_url:
        primary = _attempt_fetch(original_url, responses_dir, slug, timeout_s, original_url)
        if primary.source == FETCH_SOURCE_DOWNLOADED:
            return primary

        # An npm registry tarball URL still encodes exact package coordinates,
        # so recover its published license files from unpkg before purl.
        parsed_tarball = _parse_npm_tarball_url(original_url)
        if parsed_tarball is not None:
            package_name, version = parsed_tarball
            for candidate in _iter_npm_license_candidate_urls(package_name, version):
                fallback = _attempt_fetch(candidate, responses_dir, slug, timeout_s, original_url)
                if fallback.source == FETCH_SOURCE_DOWNLOADED:
                    return fallback

    # The inferencer's URL was missing, generic, a 404, or otherwise unusable.
    # The purl gives exact package coordinates, so try the package's own
    # published license files deterministically.
    parsed_purl = _parse_npm_purl(purl)
    if parsed_purl is not None:
        package_name, version = parsed_purl
        for candidate in _iter_npm_license_candidate_urls(package_name, version):
            fallback = _attempt_fetch(candidate, responses_dir, slug, timeout_s, original_url)
            if fallback.source == FETCH_SOURCE_DOWNLOADED:
                return fallback

    if primary is not None:
        return primary
    if purl.strip() and parsed_purl is None:
        return LicenseFetchResult.missing("unsupported_purl")
    return LicenseFetchResult.missing("no_license_url")