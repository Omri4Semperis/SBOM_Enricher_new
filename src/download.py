"""License-file download: viewer→raw rewrite, HTML reject, npm/unpkg fallback."""

from __future__ import annotations

from urllib.parse import unquote, urlsplit, urlunsplit

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
