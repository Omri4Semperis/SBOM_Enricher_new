from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CallMeta:
    """App-recorded metadata for one LLM API call.

    Written into _json.json as an app-appended block; never presented as if
    the model returned it. Fields are None when the API did not expose them.
    """
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    cost_usd: float | None = None
    elapsed_s: float = 0.0

    def json_block(self) -> dict:
        """Return a dict for JSON serialization, omitting None fields."""
        block: dict = {"model": self.model, "elapsed_s": round(self.elapsed_s, 3)}
        if self.input_tokens is not None:
            block["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            block["output_tokens"] = self.output_tokens
        if self.cache_read_tokens is not None:
            block["cache_read_tokens"] = self.cache_read_tokens
        if self.cache_write_tokens is not None:
            block["cache_write_tokens"] = self.cache_write_tokens
        if self.cost_usd is not None:
            block["cost_usd"] = round(self.cost_usd, 6)
        return block

    def cost_csv(self) -> str:
        """Return cost as a rounded string, or empty string when unknown."""
        return f"{self.cost_usd:.6f}" if self.cost_usd is not None else ""
