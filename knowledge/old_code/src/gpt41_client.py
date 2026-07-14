"""Reusable async interface to the gpt-4.1-limitless Azure OpenAI deployment.

This module is intentionally generic: it knows nothing about license
verification. It exposes a single :class:`Gpt41Client` whose ``complete``
coroutine sends an explicit system prompt plus a list of messages on every
call, so it can be reused for any future gpt-4.1 task.
"""
from __future__ import annotations

from typing import Sequence

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

import config

Message = dict[str, str]


class Gpt41Client:
    """Thin async wrapper around the gpt-4.1-limitless chat completions API.

    Construct once and share the instance across concurrent tasks; the
    underlying ``AsyncAzureOpenAI`` client is safe to reuse and pools
    connections. Authentication uses ``DefaultAzureCredential`` (no API key).
    """

    def __init__(
        self,
        *,
        endpoint: str = config.AZURE_ENDPOINT,
        deployment: str = config.GPT41_DEPLOYMENT,
        api_version: str = config.AZURE_API_VERSION,
        token_scope: str = config.AZURE_TOKEN_SCOPE,
    ) -> None:
        self._deployment = deployment
        token_provider = get_bearer_token_provider(DefaultAzureCredential(), token_scope)
        self._client = AsyncAzureOpenAI(
            api_version=api_version,
            azure_endpoint=endpoint,
            azure_ad_token_provider=token_provider,
            timeout=config.GPT41_TIMEOUT_S,
            max_retries=config.GPT41_MAX_RETRIES,
        )

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        history: Sequence[Message] | None = None,
        max_completion_tokens: int = config.GPT41_MAX_COMPLETION_TOKENS,
        temperature: float = config.GPT41_TEMPERATURE,
        top_p: float = config.GPT41_TOP_P,
        frequency_penalty: float = config.GPT41_FREQUENCY_PENALTY,
        presence_penalty: float = config.GPT41_PRESENCE_PENALTY,
    ) -> tuple[str, dict]:
        """Run one chat completion and return (assistant_text, usage_dict).

        usage_dict keys: input_tokens, output_tokens, cache_read_tokens (or empty dict).
        A full prompt is always sent: the ``system_prompt`` first, then any
        prior ``history`` messages, then the new ``user_prompt``. Raises on
        API/transport errors so callers can implement their own retry policy.
        """
        messages: list[Message] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})

        response = await self._client.chat.completions.create(
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            model=self._deployment,
        )

        text = (response.choices[0].message.content or "").strip()
        usage = {}
        if response.usage is not None:
            usage = {
                # Field names confirmed by Probe B
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                # Uncomment after Probe B confirms the field name:
                # "cache_read_tokens": getattr(
                #     getattr(response.usage, "prompt_tokens_details", None),
                #     "cached_tokens", None,
                # ),
            }
        return text, usage

    async def aclose(self) -> None:
        """Close the underlying HTTP client and its connection pool."""
        await self._client.close()
