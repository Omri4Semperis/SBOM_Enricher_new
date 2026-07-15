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


COPYRIGHT_WEB_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "copyright": {
            "type": "string",
            "description": "Verbatim copyright statement, or UNKNOWN",
        },
        "reasoning": {
            "type": "string",
            "description": "Concise sources-checked summary",
        },
    },
    "required": ["copyright", "reasoning"],
    "additionalProperties": False,
}


def copyright_web_prompt(purl: str, lib_name: str, version: str) -> tuple[str, dict]:
    """Build the Claude web-copyright prompt and its --json-schema dict."""
    purl = (purl or "").strip()
    lib = (lib_name or "").strip()
    ver = (version or "").strip()
    if purl:
        subject = f"{lib}@{ver} (purl: {purl})"
    else:
        subject = f"{lib}@{ver} (no purl)"

    text = f"""\
Who holds the copyright for {subject}?

Find a source-backed verbatim copyright statement (e.g. 'Copyright (c) 2020
Foo Inc.') from this version's upstream LICENSE/COPYING/NOTICE or source-file
headers. Use web search/fetch. Prefer package-URL (purl) as the primary key.

copyright rules:
- Return a concrete holder notice — a real person, company, or project name.
- Never return placeholder/template tokens (e.g. '<year>', '<copyright holders>').
- If unverifiable → copyright "UNKNOWN". Do not invent a holder.

Return exactly the two fields in the JSON schema. No markdown fences."""
    return text, COPYRIGHT_WEB_SCHEMA


EQUALITY_JUDGE_SYSTEM = """\
You are an equality judge for software-license audit.

Reply ONLY with a JSON object:
{"verdict": "TRUE" | "FALSE", "reasoning": "<one sentence>"}

verdict must be exactly TRUE or FALSE — never UNKNOWN. No markdown fences."""


def equality_name_prompts(inferred: str, ground_truth: str) -> tuple[str, str]:
    user = (
        "Do these two license names refer to the same license?\n\n"
        f"inferred: {inferred}\n"
        f"ground_truth: {ground_truth}\n\n"
        "Reply with the JSON object only."
    )
    return EQUALITY_JUDGE_SYSTEM, user


def equality_copyright_prompts(inferred: str, ground_truth: str) -> tuple[str, str]:
    user = (
        "Do these two copyright notices refer to the same holder/notice?\n\n"
        f"inferred: {inferred}\n"
        f"ground_truth: {ground_truth}\n\n"
        "Rules for this comparison:\n"
        "- Year tolerance: if the holder matches, a small year difference (about "
        "1-2 years) is still the same notice. Do not ignore years altogether — a "
        "large or clearly different range is not automatically equal.\n"
        "- Directional extra holders: 'and Contributors' / 'and others' counts as "
        "equal only when it names the same class of holder more fully, and the "
        "inferred side is the more elaborate one (inferred naming more than "
        "ground_truth is fine; ground_truth naming more than inferred is NOT "
        "automatically equal). A different class of added contributor is not equal.\n\n"
        "Reply with the JSON object only."
    )
    return EQUALITY_JUDGE_SYSTEM, user


def equality_url_prompts(inferred_text: str, ground_truth_text: str) -> tuple[str, str]:
    user = (
        "Is this the same license text (same license, immaterial formatting ok)?\n\n"
        f"--- inferred ---\n{inferred_text}\n\n"
        f"--- ground_truth ---\n{ground_truth_text}\n\n"
        "Reply with the JSON object only."
    )
    return EQUALITY_JUDGE_SYSTEM, user
