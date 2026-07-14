from __future__ import annotations

DEFAULT_MAX_WORKERS: int = 20
WORKERS_MIN: int = 1
WORKERS_MAX: int = 30
FETCH_MAX_WORKERS: int = 10
FETCH_TIMEOUT_S: int = 15
# Hard cap on a single `claude` CLI call (license inference or copyright
# inference). The subprocess otherwise has no timeout, so one hung web-search
# call would block the in-order output drain indefinitely. On expiry the
# process is killed and the call returns empty (treated as no response).
CLAUDE_TIMEOUT_S: int = 300
# Network resilience for license-file downloads: retry transient connection
# errors and transient HTTP statuses (429/5xx) with a linear backoff of
# FETCH_BACKOFF_BASE_S * attempt seconds between attempts.
FETCH_MAX_ATTEMPTS: int = 3
FETCH_BACKOFF_BASE_S: float = 2.0
# Network resilience for the npm registry author fallback (a small JSON GET,
# distinct from the license-file download above): retry transient connection
# errors and 429/5xx with a linear backoff of NPM_AUTHOR_BACKOFF_BASE_S *
# attempt seconds. A 404 is not retried -- it means "no such name/version",
# a normal outcome, not a transient failure.
NPM_AUTHOR_MAX_ATTEMPTS: int = 3
NPM_AUTHOR_BACKOFF_BASE_S: float = 1.5
ALLOWED_LICENSE_EXTS: frozenset[str] = frozenset({".txt", ".json", ".html", ".md"})
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
NPM_LICENSE_FILENAME_CANDIDATES: tuple[str, ...] = (
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

REQUIRED_COLUMNS: frozenset[str] = frozenset({"component_name", "purl"})

# ---------------------------------------------------------------------------
# Claude inference model selection
# ---------------------------------------------------------------------------

# Allowed values for the `claude --model <name>` flag used by the inferencer.
# These are the full model names accepted by the Claude CLI; aliases are not
# used so the choice is unambiguous in `run_info.json` and across reruns.
MODEL_CHOICES: tuple[str, ...] = (
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
)
DEFAULT_MODEL: str = "claude-opus-4-8"

# ---------------------------------------------------------------------------
# gpt-4.1-limitless (Azure OpenAI) — reusable async endpoint
# ---------------------------------------------------------------------------

AZURE_ENDPOINT: str = "https://ai-foundry-rnd-dev.cognitiveservices.azure.com/"
GPT41_DEPLOYMENT: str = "gpt-4.1-limitless"
GPT41_MODEL: str = "gpt-4.1"
AZURE_API_VERSION: str = "2024-12-01-preview"
AZURE_TOKEN_SCOPE: str = "https://cognitiveservices.azure.com/.default"

# Hard per-request limits on every gpt-4.1 call (consistency judge and
# copyright extractor). Without these the Azure OpenAI SDK retries internally
# with long exponential backoff (up to minutes) whenever Azure throttles, which
# stalls the in-order output drain. verifier.verify_consistency and
# copyright_extractor.extract_copyright already implement their own bounded
# 3-attempt loops, so SDK-level retries would only double-retry -- disable them
# (max_retries=0) and cap each individual call instead (timeout seconds). Worst
# case is JUDGE_MAX_ATTEMPTS * GPT41_TIMEOUT_S before failing closed to UNKNOWN.
GPT41_TIMEOUT_S: int = 60
GPT41_MAX_RETRIES: int = 0

# Default sampling/limit params for general gpt-4.1 calls.
GPT41_MAX_COMPLETION_TOKENS: int = 13107
GPT41_TEMPERATURE: float = 1.0
GPT41_TOP_P: float = 1.0
GPT41_FREQUENCY_PENALTY: float = 0.0
GPT41_PRESENCE_PENALTY: float = 0.0

# ---------------------------------------------------------------------------
# Final-license vs input-license equality check
# ---------------------------------------------------------------------------

LICENSE_ALIASES: dict[str, str] = {
    "mit": "MIT",
    "mit license": "MIT",
    "apache 2.0": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd 2 clause": "BSD-2-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd 3 clause": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "blue-oak-model-1.0.0": "BlueOak-1.0.0",
    "blueoak-1.0.0": "BlueOak-1.0.0",
    "blue oak 1.0.0": "BlueOak-1.0.0",
    "lgpl-3.0": "LGPL-3.0-only",
    "lgpl-3.0-only": "LGPL-3.0-only",
    "psd-2.0": "Python-2.0",
    "python-2.0": "Python-2.0",
}

EQUALITY_JUDGE_PROJECT_ENDPOINT: str = "https://ai-foundry-rnd-dev.services.ai.azure.com/api/projects/proj-ai-rnd-dev"
EQUALITY_JUDGE_AGENT_NAME: str = "llm-as-a-judge-are-values-identical"
EQUALITY_JUDGE_AGENT_VERSION: str = "2"
EQUALITY_JUDGE_MAX_ATTEMPTS: int = 3
EQUALITY_JUDGE_BACKOFF_BASE_S: float = 1.5

# Kind markers sent to the shared equality judge so it knows which comparison
# rules to apply (license vs copyright) for a given call.
EQUALITY_JUDGE_KIND_LICENSE: str = "LICENSE"
EQUALITY_JUDGE_KIND_COPYRIGHT: str = "COPYRIGHT"

# ---------------------------------------------------------------------------
# Consistency judge (gpt-4.1 functioning as a reasoning/conclusion checker)
# ---------------------------------------------------------------------------

# Max concurrent judge calls (separate from the Claude inference workers).
JUDGE_MAX_WORKERS: int = 8

# Retry budget for the judge itself: total attempts to obtain a parsable
# verdict (covers both transient API errors and unparsable judge output).
JUDGE_MAX_ATTEMPTS: int = 3
JUDGE_BACKOFF_BASE_S: float = 1.5

# Smaller completion budget — the verdict JSON is tiny.
JUDGE_MAX_COMPLETION_TOKENS: int = 500
JUDGE_TEMPERATURE: float = 0.0

JUDGE_SYSTEM_PROMPT: str = """You are a strict software-license consistency checker.

Do not use any skill, even if one is available to you.

You are given a license inference produced by another system: a predicted license identifier plus the free-text reasoning that was used to justify it.

Your ONLY job is to decide whether the reasoning INTERNALLY SUPPORTS the predicted license identifier. You are NOT deciding whether the predicted license is the objectively correct license for the package. You are checking that the conclusion does not contradict its own stated evidence.

Mark the inference INCONSISTENT when, for example:
- The reasoning describes a proprietary / commercial / vendor EULA / acceptance-required license, but the predicted identifier is an open-source license (and vice versa).
- The reasoning describes one license family but the identifier names a clearly different, incompatible one.
- The reasoning explicitly says the license could not be determined, but a concrete identifier is asserted anyway.

Mark it CONSISTENT when the predicted identifier is a reasonable, non-contradictory label for the license the reasoning describes (minor SPDX formatting differences are fine).

Reply with ONLY a single JSON object, no markdown fences and no prose before or after:
{"verdict": "CONSISTENT" or "INCONSISTENT", "explanation": "<one concise sentence>"}"""

JUDGE_USER_TEMPLATE: str = """predicted_license: {predicted_license}

reasoning:
{reasoning}

Does the reasoning internally support the predicted_license? Reply with the JSON object only."""

_LOOKUP_HIERARCHY: str = """\
Follow this strict lookup hierarchy:
1. Search deps.dev first.
2. Search the official package registry (NuGet, npm, etc.) for the specific version's metadata/manifest.
3. Check the GitHub repository at the exact version/release tag for a LICENSE file.

The license identifier and the license URL are resolved independently: confirming the
identifier at step 1 or 2 does NOT mean you should stop there for the URL. Always continue
to step 3 and locate the project's own LICENSE file in its source repository — that file,
not the registry, is the authoritative source for the license_url."""

_LICENSE_URL_RULES: str = """\
Rules for the license URL:
- The URL is downloaded automatically and its raw bytes are read as text, so it MUST serve the
  license file as raw, downloadable content — not an HTML page that merely renders the file.
  For Git-hosted projects use the raw host pinned to the release tag or commit SHA
  (e.g. 'https://raw.githubusercontent.com/<owner>/<repo>/<tag>/LICENSE'); do NOT return a
  'https://github.com/<owner>/<repo>/blob/<tag>/LICENSE' viewer URL, which returns HTML chrome
  instead of the license text. For npm packages, 'https://unpkg.com/<pkg>@<version>/LICENSE'
  serves the file as raw text.
- Pin the URL to the exact version's release tag or commit SHA — never a moving branch such as
  'main', 'master', or 'HEAD', whose content can change after the release.
- Do not treat a tag as automatic ground truth: confirm the literal tag string for THIS version
  (naming conventions can change mid-project, e.g. 'v1.2.3' vs '1.2.3'). If the expected tag is
  missing or was moved/recreated after release, resolve another raw source for the exact version
  rather than guessing a tag.
- Return a URL that serves raw license TEXT. Avoid archive and package download URLs, including
    '.tar.gz', '.tgz', '.zip', '.nupkg', '.whl', and npm registry tarballs such as
    'https://registry.npmjs.org/<pkg>/-/<name>-<version>.tgz'. The downstream step reads the URL as
    text and cannot open an archive. When only an archive ships the license, prefer the same file
    exposed through the project's source repository raw host instead.
- For npm packages, prefer the project source repository's raw LICENSE file. If that cannot be
    resolved, 'https://unpkg.com/<pkg>@<version>/LICENSE' is an acceptable raw package-file fallback.
- Do not return generic license-template pages; they are unusable for copyright extraction because
    they contain boilerplate rather than the package's holder. Examples include
    'opensource.org/license/...', 'opensource.org/licenses/...', 'spdx.org/licenses/...',
    'choosealicense.com/licenses/...', 'licenses.nuget.org/...', and 'tldrlegal.com/...'.
- If the registry page links to such a generic aggregator URL, do not simply copy it — go find
    the actual LICENSE file in the source repository instead."""

_LICENSE_RULES: str = """\
Rules for License Formatting:
- Use standard SPDX License Expression Syntax (e.g., 'MIT OR Apache-2.0', 'GPL-2.0-only WITH Classpath-exception-2.0') to represent dual or complex licensing.
- If the license is an official open-source license, return its valid, modern SPDX identifier (e.g., 'LGPL-3.0-only').
- If the license is proprietary, commercial, or a custom vendor EULA, map it to a clean shorthand identifier like 'Microsoft-DotNet-Library', 'Microsoft-EULA', or 'DevExpress-EULA'. Do not use 'LicenseRef-' prefixes.
- If a package registry page links to a legacy proprietary license but the source code for that exact version has been explicitly open-sourced, favor the open-source license.
- A package's self-description — "port of", "based on", "compatible with", or "reimplementation of" another project — tells you NOTHING about its own license. It may deliberately match the referenced project (e.g. npm 'argparse'@2.x relicensed itself to Python-2.0 to match the CPython module it reimplements) or differ entirely (its own v1.x was MIT). Always resolve the license from the LICENSE/manifest of the EXACT version being classified — never infer it from the description in either direction.
- If the package is private or requires authenticated registry access and has no public resolution path, return 'UNKNOWN' rather than guessing from adjacent public documentation.

Only return 'UNKNOWN' if no authoritative registry entry, source repository, or historical license record can be found, or if the package/version does not exist. Do not guess."""


def build_query_prompt(
    lib_name: str,
    version: str,
    purl: str,
    need_license: bool,
    need_url: bool,
) -> str:
    """Build a Claude inferencer prompt requesting only the missing fields.

    Always includes a ``reasoning`` field in the requested JSON reply regardless
    of which business fields are needed.
    """
    purl_clean = purl.strip()
    purl_part = f" (purl: {purl_clean})" if purl_clean and purl_clean != "—" else ""
    lib = lib_name.strip()
    ver = version.strip()

    if need_license and need_url:
        question = f"What is the software license for {lib}@{ver}{purl_part}?"
    elif need_license:
        question = (
            f"What is the software license identifier for {lib}@{ver}{purl_part}?"
            " (The license URL is already known; provide only the license identifier.)"
        )
    else:
        question = (
            f"What is the direct URL to the license file for {lib}@{ver}{purl_part}?"
            " (The license identifier is already known; provide only the URL.)"
        )

    # Build the JSON reply format.
    fields: list[str] = []
    if need_license:
        fields.append('"license": "<SPDX expression or shorthand>"')
    if need_url:
        fields.append(
            '"license_url": "<direct RAW-content URL to the LICENSE file in the project'
            "'s own source repository at the resolved version/tag"
            ' (e.g. a raw.githubusercontent.com link pinned to the tag/SHA, not a'
            " github.com blob viewer page). Only fall back to a generic"
            " license-template/registry page URL if no project-specific LICENSE file"
            ' can be found. Empty string if none found.>"'
        )
    fields.append('"reasoning": "<concise summary of sources checked>"')
    json_format = "{" + ", ".join(fields) + "}"

    parts = [
        question,
        "",
        _LOOKUP_HIERARCHY,
    ]
    if need_license:
        parts += ["", _LICENSE_RULES]
    if need_url:
        parts += ["", _LICENSE_URL_RULES]
    parts += [
        "",
        f"Reply ONLY with a JSON object in this exact format:\n{json_format}",
        "",
        "No markdown fences, no prose before or after the JSON object.",
        "",
        "DO NOT spend more than $0.5 on this task.",
    ]
    return "\n".join(parts)

def build_copyright_query_prompt(
    lib_name: str,
    version: str,
    purl: str,
) -> str:
    """Build a Claude prompt requesting the copyright holder directly.

    Used only as the last-resort copyright fallback, after the LICENSE file
    and (for npm) the registry author have both failed to yield a holder.
    """
    purl_clean = purl.strip()
    purl_part = f" (purl: {purl_clean})" if purl_clean and purl_clean != "—" else ""
    lib = lib_name.strip()
    ver = version.strip()

    question = f"Who is the copyright holder for {lib}@{ver}{purl_part}?"

    rules = """\
Resolve the copyright holder from the project's own upstream LICENSE, COPYING, or NOTICE \
file at the exact version, or from its source-file copyright headers. Return a concrete \
holder -- a real person, company, or project name (e.g. 'Google Inc.', 'The FreeType \
Project', 'Igor Sysoev') -- never a placeholder or template token. Reply with the exact \
string UNKNOWN if no concrete holder can be verified. Do not invent a holder."""

    json_format = '{"copyright": "<copyright holder, or UNKNOWN>", "reasoning": "<concise summary of sources checked>"}'

    parts = [
        question,
        "",
        _LOOKUP_HIERARCHY,
        "",
        rules,
        "",
        f"Reply ONLY with a JSON object in this exact format:\n{json_format}",
        "",
        "No markdown fences, no prose before or after the JSON object.",
        "",
        "DO NOT spend more than $0.5 on this task.",
    ]
    return "\n".join(parts)

# ---------------------------------------------------------------------------
# Copyright extraction (gpt-4.1 second-step)
# ---------------------------------------------------------------------------

# Marker written to the output when copyright cannot be determined.
COPYRIGHT_UNKNOWN: str = "UNKNOWN"

# Reasons stored alongside COPYRIGHT_UNKNOWN so downstream consumers can
# distinguish why extraction failed without parsing free-text.
COPYRIGHT_REASON_NO_FILE: str = "UNKNOWN_no_file"
COPYRIGHT_REASON_EMPTY_FILE: str = "UNKNOWN_empty_file"
COPYRIGHT_REASON_RETRY_EXHAUSTED: str = "UNKNOWN_retry_exhausted"
COPYRIGHT_REASON_NO_COPYRIGHT_FOUND: str = "UNKNOWN_no_copyright_found"
# The fetched file was a generic license template whose copyright line is an
# unfilled placeholder (e.g. "Copyright (c) <year> <copyright holders>").
# Returning that verbatim would be wrong, so extraction fails closed to UNKNOWN.
COPYRIGHT_REASON_PLACEHOLDER: str = "UNKNOWN_placeholder_template"
COPYRIGHT_REASON_EXTRACTED: str = "extracted"
COPYRIGHT_REASON_INPUT_VALUE: str = "input_value"
# Deterministic fallback: the LICENSE file itself yielded no holder (any of
# the UNKNOWN_* reasons above) but the row is npm, so the holder is read from
# npm registry metadata (package.json's `author`, mirrored to the registry)
# instead. Never overrides input-provided or file-extracted copyright.
COPYRIGHT_REASON_NPM_AUTHOR: str = "npm_author"
# Last-resort fallback: neither the LICENSE file nor (for npm) the registry
# author yielded a holder, so a web-enabled Claude call is asked directly for
# the project's copyright holder. Bottom of the precedence ladder -- never
# overrides input-provided, file-extracted, or npm-author copyright.
COPYRIGHT_REASON_INFERRED: str = "inferred"

COPYRIGHT_MAX_ATTEMPTS: int = 3
COPYRIGHT_BACKOFF_BASE_S: float = 1.5
COPYRIGHT_MAX_COMPLETION_TOKENS: int = 1000

# Dedicated worker pool for the last-resort copyright *inference* fallback
# (web-enabled Claude call). It runs on its own semaphore rather than sharing
# the license-inference pool, so a run saturated with license inference cannot
# starve the copyright-infer step and block a row's final stage indefinitely.
COPYRIGHT_INFER_MAX_WORKERS: int = 8

COPYRIGHT_SYSTEM_PROMPT: str = """You are a software-license copyright extractor.

Do not use any skill, even if one is available to you.

You are given the text of a software license file. Extract all copyright notice lines \
from it verbatim (e.g. 'Copyright (c) 2023 Foo Inc.'). If there are multiple notices, \
join them with a newline.

A REAL copyright notice names a concrete holder — a real person, company, or project name \
(e.g. 'Copyright (c) 2023 Foo Inc.', 'Copyright (c) Sindre Sorhus', or \
'Copyright © The Foo Project'). A year is common but OPTIONAL: a notice that names a concrete \
holder is real even when it has no year. Do NOT return UNKNOWN merely because a year is missing.

Many license files are instead generic, unfilled templates whose copyright line is only a \
placeholder, for example: 'Copyright (c) <year> <copyright holders>', \
'Copyright [yyyy] [name of copyright owner]', 'Copyright (c) [year] [fullname]', or any similar \
text that uses <...>, [...], or {...} placeholders, or bare uppercase stand-ins like \
YEAR / AUTHOR / FULLNAME / NAME OF COPYRIGHT OWNER, instead of a real holder name. Placeholder \
text is NOT a copyright notice — it is boilerplate from a license template, not the project's \
own copyright.

Reply with the exact string UNKNOWN when the only copyright line is such a placeholder, or \
when no copyright notice is present at all. Never return placeholder/template text as if it \
were a real copyright: returning UNKNOWN is strongly preferred over returning something \
wrong.

Reply ONLY with a JSON object in this exact format:
{"copyright": "<extracted copyright text, or UNKNOWN>", "reasoning": "<one sentence>"}

No markdown fences, no prose before or after the JSON object."""

COPYRIGHT_USER_TEMPLATE: str = """License file contents:

{license_text}

Extract the copyright notice(s). Reply with the JSON object only."""

# ---------------------------------------------------------------------------
# LLM Model Pricing — per-million-token rates in USD
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    """Per-million-token prices in USD for one model.

    Set any field to None if that pricing tier does not apply or is unknown.
    Prices come from the vendor's pricing page and must be kept up to date.
    """

    input_usd_per_m: float | None = None  # regular input (prompt) tokens
    output_usd_per_m: float | None = None  # output (completion) tokens
    cache_read_usd_per_m: float | None = None  # cache-read (prompt cache hit) tokens
    cache_write_usd_per_m: float | None = None  # cache-write (cache creation) tokens


MODEL_PRICING: dict[str, ModelPricing] = {
    # Claude models — cost already comes from CLI total_cost_usd, but token
    # prices are listed here so per-token breakdowns can be computed if the
    # CLI ever exposes individual token counts.
    # Source: https://www.anthropic.com/pricing  (verify before use)
    "claude-haiku-4-5": ModelPricing(
        input_usd_per_m=0.80,
        output_usd_per_m=4.00,
        cache_read_usd_per_m=0.08,
        cache_write_usd_per_m=1.00,
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_usd_per_m=3.00,
        output_usd_per_m=15.00,
        cache_read_usd_per_m=0.30,
        cache_write_usd_per_m=3.75,
    ),
    "claude-opus-4-8": ModelPricing(
        input_usd_per_m=15.00,
        output_usd_per_m=75.00,
        cache_read_usd_per_m=1.50,
        cache_write_usd_per_m=18.75,
    ),
    # GPT-4.1-limitless (Azure OpenAI) — cost computed from token counts.
    # Source: Azure AI Foundry pricing page  (verify before use)
    "gpt-4.1": ModelPricing(
        input_usd_per_m=2.00,
        output_usd_per_m=8.00,
        cache_read_usd_per_m=0.50,
    ),
    # Shared equality judge (license OR copyright) — Azure AI Projects agent
    # reference. Backed by Claude Haiku 4.5. The Azure AI Projects responses API
    # exposes input_tokens/output_tokens, so cost is computed from these rates.
    # Source: vendor pricing for the agent's backing model  (verify before use)
    "llm-as-a-judge-are-values-identical": ModelPricing(
        input_usd_per_m=1.00,
        output_usd_per_m=5.00,
    ),
}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Return USD cost for one call, or None if pricing is not configured."""
    pricing = MODEL_PRICING.get(model)
    # Return None (not 0.0) when no usable price exists, so an unpriced call is
    # recorded as "unknown cost" rather than a misleadingly free one.
    if pricing is None or all(
        rate is None
        for rate in (
            pricing.input_usd_per_m,
            pricing.output_usd_per_m,
            pricing.cache_read_usd_per_m,
            pricing.cache_write_usd_per_m,
        )
    ):
        return None
    cost = 0.0
    # NOTE: this subtraction assumes the API's input/prompt token count already
    # INCLUDES cache-read and cache-write tokens (true for Azure OpenAI). It is
    # NOT true for Anthropic, where cache tokens are separate fields. Claude cost
    # comes from the CLI's authoritative total_cost_usd, so this path is not used
    # for Claude; do not feed Anthropic token counts here.
    regular_input_tokens = max(input_tokens - cache_read_tokens - cache_write_tokens, 0)
    if pricing.input_usd_per_m is not None:
        cost += regular_input_tokens * pricing.input_usd_per_m / 1_000_000
    if pricing.cache_read_usd_per_m is not None:
        cost += cache_read_tokens * pricing.cache_read_usd_per_m / 1_000_000
    if pricing.cache_write_usd_per_m is not None:
        cost += cache_write_tokens * pricing.cache_write_usd_per_m / 1_000_000
    if pricing.output_usd_per_m is not None:
        cost += output_tokens * pricing.output_usd_per_m / 1_000_000
    return cost
