"""Reusable async GPT-4.1 client (fixed Azure deployment)."""

from __future__ import annotations

import json
import re

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import APIConnectionError, APITimeoutError, AsyncAzureOpenAI, RateLimitError

from retry import with_retries

AZURE_ENDPOINT = "https://ai-foundry-rnd-dev.cognitiveservices.azure.com/"
GPT41_DEPLOYMENT = "gpt-4.1-limitless"
AZURE_API_VERSION = "2024-12-01-preview"
AZURE_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class ParseFailure(Exception):
    pass


class TransientFailure(Exception):
    pass


class HardFailure(Exception):
    pass


def _classify(exc: BaseException) -> str:
    if isinstance(exc, HardFailure):
        return "hard"
    if isinstance(exc, ParseFailure):
        return "parse"
    if isinstance(exc, TransientFailure):
        return "transient"
    if isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError)):
        return "transient"
    return "hard"


def _parse_json_content(text: str) -> dict:
    raw = (text or "").strip()
    raw = _FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ParseFailure(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ParseFailure("JSON root is not an object")
    return data


class Gpt41Client:
    """Thin async wrapper around the fixed gpt-4.1-limitless deployment."""

    def __init__(self) -> None:
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), AZURE_TOKEN_SCOPE
        )
        self._client = AsyncAzureOpenAI(
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_ENDPOINT,
            azure_ad_token_provider=token_provider,
            timeout=60,
            max_retries=0,
        )

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Chat once with retries; return parsed JSON object."""

        async def once() -> dict:
            try:
                response = await self._client.chat.completions.create(
                    model=GPT41_DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_completion_tokens=1000,
                )
            except (APIConnectionError, APITimeoutError, RateLimitError):
                raise
            except Exception as e:  # noqa: BLE001 — map unknown SDK errors
                raise HardFailure(str(e)) from e

            try:
                content = response.choices[0].message.content or ""
            except (IndexError, AttributeError) as e:
                raise ParseFailure(f"empty/malformed response: {e}") from e
            return _parse_json_content(content)

        return await with_retries(once, classify=_classify)
