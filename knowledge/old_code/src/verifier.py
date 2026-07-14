"""Consistency-check layer built on top of the generic gpt-4.1 client.

The judge confirms that an inference's stated reasoning internally supports its
predicted license identifier. It does NOT decide whether the license is the
objectively correct one. A failed judgement (INCONSISTENT, or no parsable
verdict after all retries) downgrades the final license to ``UNKNOWN``.
"""
from __future__ import annotations

import asyncio
import time

import config
from cost_tracking import CallMeta
from gpt41_client import Gpt41Client
from response_parser import (
    VERDICT_CONSISTENT,
    VERDICT_ERROR,
    VerificationResult,
    parse_judge_response,
)

UNKNOWN_LICENSE = "UNKNOWN"

# Predictions that carry no concrete claim worth checking for consistency.
_NON_JUDGEABLE = {"", "UNKNOWN", "[PARSE ERROR]"}


def _should_judge(predicted_license: str, parse_error: bool) -> bool:
    if parse_error:
        return False
    return predicted_license.strip().upper() not in _NON_JUDGEABLE


async def verify_consistency(
    client: Gpt41Client,
    sem: asyncio.Semaphore,
    predicted_license: str,
    reasoning: str,
    *,
    parse_error: bool = False,
) -> VerificationResult:
    """Judge whether ``reasoning`` supports ``predicted_license``.

    Skips the call when there is nothing meaningful to judge. Retries the judge
    itself on transient API errors and on unparsable verdicts, with exponential
    backoff, up to ``config.JUDGE_MAX_ATTEMPTS``.
    """
    if not _should_judge(predicted_license, parse_error):
        return VerificationResult.skipped(predicted_license)

    user_prompt = config.JUDGE_USER_TEMPLATE.format(
        predicted_license=predicted_license.strip(),
        reasoning=(reasoning or "").strip() or "(no reasoning provided)",
    )

    start = time.monotonic()
    last_raw = ""
    last_error = ""

    for attempt in range(1, config.JUDGE_MAX_ATTEMPTS + 1):
        try:
            async with sem:
                raw, usage = await client.complete(
                    config.JUDGE_SYSTEM_PROMPT,
                    user_prompt,
                    max_completion_tokens=config.JUDGE_MAX_COMPLETION_TOKENS,
                    temperature=config.JUDGE_TEMPERATURE,
                )
            last_raw = raw
            verdict, explanation = parse_judge_response(raw)
        except Exception as exc:  # API/transport error or unparsable verdict
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < config.JUDGE_MAX_ATTEMPTS:
                await asyncio.sleep(config.JUDGE_BACKOFF_BASE_S * attempt)
            continue

        elapsed = time.monotonic() - start
        consistent = verdict == VERDICT_CONSISTENT
        final_license = predicted_license if consistent else UNKNOWN_LICENSE

        judge_cost = config.compute_cost(
            model=config.GPT41_MODEL,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_tokens", 0),
        )

        return VerificationResult(
            verdict=verdict,
            consistent=consistent,
            judge_reasoning=explanation,
            judge_raw=raw,
            judge_elapsed_s=elapsed,
            judge_attempts=attempt,
            final_license=final_license,
            judge_meta=CallMeta(
                model=config.GPT41_MODEL,
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                cache_read_tokens=usage.get("cache_read_tokens"),
                cost_usd=judge_cost,
                elapsed_s=elapsed,
            ),
        )

    # Exhausted all attempts without a parsable verdict: fail closed to UNKNOWN.
    return VerificationResult(
        verdict=VERDICT_ERROR,
        consistent=None,
        judge_reasoning=f"Judge unavailable after {config.JUDGE_MAX_ATTEMPTS} attempts: {last_error}",
        judge_raw=last_raw,
        judge_elapsed_s=time.monotonic() - start,
        judge_attempts=config.JUDGE_MAX_ATTEMPTS,
        final_license=UNKNOWN_LICENSE,
        judge_meta=None,
    )
