"""Prompt strings and JSON schemas for LLM stages."""

from __future__ import annotations

LICENSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "license_name": {
            "type": "string",
            "description": "SPDX id / shorthand, or UNKNOWN",
        },
        "license_code_url": {
            "type": "string",
            "description": "Raw downloadable LICENSE URL, or empty string",
        },
        "reasoning": {
            "type": "string",
            "description": "Concise sources-checked summary",
        },
    },
    "required": ["license_name", "license_code_url", "reasoning"],
    "additionalProperties": False,
}


def license_prompt(purl: str, lib_name: str, version: str) -> tuple[str, dict]:
    """Build the license-inference prompt and its --json-schema dict."""
    purl = (purl or "").strip()
    lib = (lib_name or "").strip()
    ver = (version or "").strip()
    if purl:
        subject = f"{lib}@{ver} (purl: {purl})"
    else:
        subject = f"{lib}@{ver} (no purl)"

    text = f"""\
What is the software license for {subject}?

Identify license_name and a raw downloadable license_code_url for this exact
version. Use web search/fetch. Prefer package-URL (purl) as the primary key;
lib/version are secondary context.

Lookup order:
1. deps.dev for this package/version
2. Official registry metadata for this version
3. The project's own LICENSE/COPYING file in source at the matching tag/SHA

Resolve name and URL independently — a registry SPDX id does not finish the
URL search; still find the project's LICENSE file when possible.

license_name rules:
- Prefer modern SPDX identifiers (e.g. MIT, Apache-2.0, GPL-3.0-only).
- Proprietary/custom EULAs → short shorthand (e.g. Microsoft-EULA), no LicenseRef-.
- Never infer license from "port of" / "based on" descriptions; use this version's
  LICENSE/manifest only.
- If unverifiable → license_name "UNKNOWN".

license_code_url rules:
- Must serve raw license text (e.g. raw.githubusercontent.com/.../LICENSE), not
  an HTML viewer (github.com/.../blob/...), not a registry archive/tarball.
- Pin to the release tag or commit SHA for this version — not main/master/HEAD.
- Avoid generic template pages (spdx.org, opensource.org, choosealicense, etc.).
- If no project file can be found → empty string.

Return exactly the three fields in the JSON schema. No markdown fences."""
    return text, LICENSE_SCHEMA


COPYRIGHT_SYSTEM = """\
You are a software-license copyright extractor.

You are given the text of a software license file. Extract all copyright
notice lines from it verbatim (e.g. 'Copyright (c) 2023 Foo Inc.'). If there
are multiple notices, join them with a newline.

A REAL copyright notice names a concrete holder — a person, company, or
project name. A year is common but optional: a notice that names a concrete
holder is real even without a year. Do NOT return UNKNOWN merely because a
year is missing.

Many license files are generic unfilled templates whose copyright line is
only a placeholder, for example 'Copyright (c) <year> <copyright holders>'
or 'Copyright [yyyy] [name of copyright owner]'. Placeholder/template text
is NOT a copyright notice — reply UNKNOWN instead. Prefer UNKNOWN over
returning something wrong.

Reply ONLY with a JSON object:
{"copyright": "<extracted copyright text, or UNKNOWN>", "reasoning": "<one sentence>"}

No markdown fences, no prose before or after."""


def copyright_prompt(license_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for copyright extraction."""
    user = (
        "License file contents:\n\n"
        f"{license_text}\n\n"
        "Extract the copyright notice(s). Reply with the JSON object only."
    )
    return COPYRIGHT_SYSTEM, user
