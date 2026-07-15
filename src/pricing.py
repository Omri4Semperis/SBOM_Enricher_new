"""Ops pricing constants (source-only; not config)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

UNKNOWN_COST = "unknown"


@dataclass
class CallMeta:
    """Accumulator for billable LLM call cost/raw metadata."""

    known_usd: float = 0.0
    billable_calls: int = 0
    unknown_calls: int = 0
    raws: list[str] = field(default_factory=list)

    def total_usd(self) -> float | None:
        return None if self.unknown_calls > 0 else self.known_usd

    def add_call(self, *, cost_usd: float | None, raw: str) -> None:
        self.billable_calls += 1
        self.raws.append(raw)
        if cost_usd is None:
            self.unknown_calls += 1
        else:
            self.known_usd += cost_usd

    def cost_cell(self) -> str:
        return format_cost(self.total_usd())


def combine(metas: Iterable[CallMeta]) -> CallMeta:
    out = CallMeta()
    for m in metas:
        out.known_usd += m.known_usd
        out.billable_calls += m.billable_calls
        out.unknown_calls += m.unknown_calls
        out.raws.extend(m.raws)
    return out


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_m: float | None = None
    output_usd_per_m: float | None = None
    cache_read_usd_per_m: float | None = None
    cache_write_usd_per_m: float | None = None


# Ported from old config.MODEL_PRICING — GPT-4.1 used for copyright/equality.
MODEL_PRICING: dict[str, ModelPricing] = {
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
    "gpt-4.1": ModelPricing(
        input_usd_per_m=2.00,
        output_usd_per_m=8.00,
        cache_read_usd_per_m=0.50,
    ),
}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """USD for one call, or None when price is unknown (never 0 for missing)."""
    pricing = MODEL_PRICING.get(model)
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
    # Azure-style: input count includes cache tokens.
    regular = max(input_tokens - cache_read_tokens - cache_write_tokens, 0)
    cost = 0.0
    if pricing.input_usd_per_m is not None:
        cost += regular * pricing.input_usd_per_m / 1_000_000
    if pricing.cache_read_usd_per_m is not None:
        cost += cache_read_tokens * pricing.cache_read_usd_per_m / 1_000_000
    if pricing.cache_write_usd_per_m is not None:
        cost += cache_write_tokens * pricing.cache_write_usd_per_m / 1_000_000
    if pricing.output_usd_per_m is not None:
        cost += output_tokens * pricing.output_usd_per_m / 1_000_000
    return cost


def format_cost(cost: float | None) -> str:
    """CSV/summary cell: numeric string or unknown marker (never '0' for missing)."""
    if cost is None:
        return UNKNOWN_COST
    return f"{cost:.6f}"
