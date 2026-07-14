from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

import config
from cost_tracking import CallMeta


@dataclass(frozen=True)
class EqualityJudgeResult:
    """Full result of one equality-judge API call.

    ``verdict`` is the parsed YES/NO answer; ``meta`` holds cost/token
    information. ``query`` is the exact string sent to the model and
    ``raw_response`` is the model's verbatim text output — both preserved for
    debugging in the per-row response files.
    """

    verdict: bool
    meta: CallMeta | None
    query: str = field(default="")
    raw_response: str = field(default="")


class EqualityJudgeClient:
    """Async wrapper around the shared Azure AI Projects equality-judge agent.

    The agent handles two independent kinds of comparison — license identifiers
    and copyright notices — selected per call via ``kind``. Each call judges
    exactly one kind; the two comparisons are never combined in a single call.
    """

    def __init__(
        self,
        *,
        endpoint: str = config.EQUALITY_JUDGE_PROJECT_ENDPOINT,
        agent_name: str = config.EQUALITY_JUDGE_AGENT_NAME,
        agent_version: str = config.EQUALITY_JUDGE_AGENT_VERSION,
    ) -> None:
        self._agent_name = agent_name
        self._agent_version = agent_version
        self._project_client = AIProjectClient(
            endpoint=endpoint,
            credential=DefaultAzureCredential(),
        )
        self._openai_client = self._project_client.get_openai_client()

    def _compare_sync(
        self, kind: str, expected: str, predicted: str
    ) -> tuple[bool, dict | None, str, str]:
        query = f"KIND: {kind}\n{expected}\nvs\n{predicted}"
        response = self._openai_client.responses.create(
            input=[
                {
                    "role": "user",
                    "content": query,
                }
            ],
            extra_body={
                "agent_reference": {
                    "name": self._agent_name,
                    "version": self._agent_version,
                    "type": "agent_reference",
                }
            },
        )
        raw_output = (response.output_text or "").strip()
        verdict = raw_output.upper()
        if verdict not in {"YES", "NO"}:
            raise ValueError(f"unexpected equality-judge verdict: {verdict!r}")

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage is not None:
            usage = {
                "input_tokens": getattr(raw_usage, "input_tokens", None),
                "output_tokens": getattr(raw_usage, "output_tokens", None),
            }
        return verdict == "YES", usage, query, raw_output

    async def are_identical(
        self, expected: str, predicted: str, *, kind: str
    ) -> EqualityJudgeResult:
        start = time.monotonic()
        last_error = ""
        for attempt in range(1, config.EQUALITY_JUDGE_MAX_ATTEMPTS + 1):
            try:
                verdict, usage, query, raw_output = await asyncio.to_thread(
                    self._compare_sync, kind, expected, predicted
                )
                elapsed = time.monotonic() - start
                meta: CallMeta | None = None
                if usage is not None:
                    cost = config.compute_cost(
                        config.EQUALITY_JUDGE_AGENT_NAME,
                        input_tokens=usage.get("input_tokens") or 0,
                        output_tokens=usage.get("output_tokens") or 0,
                    )
                    meta = CallMeta(
                        model=config.EQUALITY_JUDGE_AGENT_NAME,
                        input_tokens=usage.get("input_tokens"),
                        output_tokens=usage.get("output_tokens"),
                        cost_usd=cost,
                        elapsed_s=elapsed,
                    )
                elif elapsed > 0:
                    meta = CallMeta(model=config.EQUALITY_JUDGE_AGENT_NAME, elapsed_s=elapsed)
                return EqualityJudgeResult(verdict=verdict, meta=meta, query=query, raw_response=raw_output)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < config.EQUALITY_JUDGE_MAX_ATTEMPTS:
                    await asyncio.sleep(config.EQUALITY_JUDGE_BACKOFF_BASE_S * attempt)
        return EqualityJudgeResult(verdict=False, meta=None)

    async def aclose(self) -> None:
        close = getattr(self._openai_client, "close", None)
        if callable(close):
            await asyncio.to_thread(close)
        project_close = getattr(self._project_client, "close", None)
        if callable(project_close):
            await asyncio.to_thread(project_close)
