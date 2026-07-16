"""Locked LLM retry/backoff: transient vs parse vs hard."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from eventlog import emit

T = TypeVar("T")

Kind = str  # "transient" | "parse" | "hard"

TRANSIENT_ATTEMPTS = 3
PARSE_ATTEMPTS = 2
TRANSIENT_SLEEP_1 = 2.0
TRANSIENT_SLEEP_2_LO = 3.0
TRANSIENT_SLEEP_2_HI = 8.0
PARSE_SLEEP = 1.0


async def with_retries(
    fn: Callable[[], Awaitable[T]],
    *,
    transient_attempts: int = TRANSIENT_ATTEMPTS,
    parse_attempts: int = PARSE_ATTEMPTS,
    classify: Callable[[BaseException], Kind],
) -> T:
    """Call async ``fn`` with the locked retry policy.

    ``classify(exc)`` must return ``\"transient\"``, ``\"parse\"``, or ``\"hard\"``.
    Hard failures re-raise immediately. Exhausted budgets re-raise the last error.
    """
    transient_used = 0
    parse_used = 0
    while True:
        try:
            return await fn()
        except BaseException as exc:
            kind = classify(exc)
            if kind == "hard":
                raise
            if kind == "transient":
                transient_used += 1
                if transient_used >= transient_attempts:
                    raise
                if transient_used == 1:
                    sleep_s = TRANSIENT_SLEEP_1
                else:
                    sleep_s = random.uniform(TRANSIENT_SLEEP_2_LO, TRANSIENT_SLEEP_2_HI)
                emit("retry", kind="transient", n=transient_used, sleep_s=round(sleep_s, 3))
                await asyncio.sleep(sleep_s)
            elif kind == "parse":
                parse_used += 1
                if parse_used >= parse_attempts:
                    raise
                emit("retry", kind="parse", n=parse_used, sleep_s=PARSE_SLEEP)
                await asyncio.sleep(PARSE_SLEEP)
            else:
                raise ValueError(f"unknown failure kind: {kind!r}") from exc
