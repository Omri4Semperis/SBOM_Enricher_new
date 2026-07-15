"""Probe representative URLs to confirm failure modes and test candidate fixes.

- Confirms GT 'landing page' URLs return HTML (why content-compare fails).
- Confirms a few inferred URLs that 404'd.
- Tests the NuGet flat-container nuspec API as a deterministic license source
  for NuGet packages (the biggest empty-inference bucket).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
from download import looks_like_html  # noqa: E402

OUT = REPO / "ad_hoc_scripts" / "ad_hoc_scripts_output"
OUT.mkdir(parents=True, exist_ok=True)

HEADERS_NONE: dict[str, str] = {}
HEADERS_UA = {"User-Agent": "Mozilla/5.0 (compatible; sbom-enricher/1.0)"}

GT_LANDING = [
    ("golang pkg.go.dev", "https://pkg.go.dev/golang.org/x/sys@v0.29.0"),
    ("apk alpine pkg", "https://pkgs.alpinelinux.org/package/edge/main/x86/tzdata"),
    ("nuget License", "https://www.nuget.org/packages/Microsoft.AspNet.WebApi.Core/5.2.7/License"),
    ("ubuntu changelog", "https://changelogs.ubuntu.com/changelogs/pool/main/g/glibc/glibc_2.39-0ubuntu8.7/"),
    ("github blob", "https://github.com/dotnet/ef6/blob/6.2.0/License.txt"),
]

INF_FAILED = [
    ("binutils COPYING", "https://raw.githubusercontent.com/bminor/binutils-gdb/binutils-2_45_1/COPYING"),
    ("busybox git", "https://git.busybox.net/busybox/plain/LICENSE?h=1_37_0"),
]

# NuGet packages whose inferred URL was EMPTY -> can nuspec give us the license?
NUGET_PKGS = [
    ("System.Collections", "4.3.0"),
    ("Microsoft.AspNet.WebApi.Core", "5.2.7"),
    ("EntityFramework", "6.2.0"),
    ("Newtonsoft.Json", "13.0.3"),  # control: known MIT with license file
]


def probe(url: str, headers: dict) -> str:
    try:
        r = requests.get(url, timeout=30, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR {exc.__class__.__name__}: {exc}"
    ct = r.headers.get("Content-Type", "")
    html = looks_like_html(r.content, ct)
    return f"HTTP {r.status_code}  ct={ct!r}  looks_html={html}  bytes={len(r.content)}"


def nuget_nuspec(pkg: str, version: str) -> str:
    lid = pkg.lower()
    url = f"https://api.nuget.org/v3-flatcontainer/{lid}/{version}/{lid}.nuspec"
    try:
        r = requests.get(url, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR {exc}"
    if r.status_code != 200:
        return f"HTTP {r.status_code} @ {url}"
    text = r.text
    # crude extraction of <license> and <licenseUrl> and <repository url=...>
    import re
    lic = re.search(r"<license[^>]*>(.*?)</license>", text, re.S)
    lic_type = re.search(r'<license type="([^"]+)"', text)
    licurl = re.search(r"<licenseUrl>(.*?)</licenseUrl>", text, re.S)
    repo = re.search(r'<repository[^>]*url="([^"]+)"', text)
    proj = re.search(r"<projectUrl>(.*?)</projectUrl>", text, re.S)
    parts = [
        f"license={lic.group(1).strip() if lic else None} (type={lic_type.group(1) if lic_type else None})",
        f"licenseUrl={licurl.group(1).strip() if licurl else None}",
        f"repo={repo.group(1) if repo else None}",
        f"projectUrl={proj.group(1).strip() if proj else None}",
    ]
    return " | ".join(parts)


def main() -> None:
    lines: list[str] = []

    def out(s=""):
        lines.append(s)
        print(s)

    out("=== GT landing-page URLs: no headers vs browser UA ===")
    for name, url in GT_LANDING:
        out(f"- {name}: {url}")
        out(f"    no-UA : {probe(url, HEADERS_NONE)}")
        out(f"    w/ UA : {probe(url, HEADERS_UA)}")
    out()

    out("=== Inferred URLs that failed ===")
    for name, url in INF_FAILED:
        out(f"- {name}: {url}")
        out(f"    no-UA : {probe(url, HEADERS_NONE)}")
    out()

    out("=== NuGet nuspec API (candidate fallback for empty-inference nuget) ===")
    for pkg, ver in NUGET_PKGS:
        out(f"- {pkg}@{ver}: {nuget_nuspec(pkg, ver)}")
    out()

    (OUT / "url_verification.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
