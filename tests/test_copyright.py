import asyncio
from unittest.mock import AsyncMock, MagicMock

import gpt41_client
import pytest
import retry
from gpt41_client import Gpt41Client, ParseFailure


def _mock_azure(monkeypatch, content: str | list[str]):
    """Patch credential + AsyncAzureOpenAI; content is one reply or a sequence."""
    replies = content if isinstance(content, list) else [content]
    state = {"i": 0}

    async def create(**_kwargs):
        i = min(state["i"], len(replies) - 1)
        text = replies[i]
        state["i"] += 1
        msg = MagicMock()
        msg.content = text
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=create)

    monkeypatch.setattr(gpt41_client, "DefaultAzureCredential", MagicMock())
    monkeypatch.setattr(
        gpt41_client, "get_bearer_token_provider", MagicMock(return_value=lambda: "tok")
    )
    monkeypatch.setattr(gpt41_client, "AsyncAzureOpenAI", MagicMock(return_value=client))
    monkeypatch.setattr(retry.asyncio, "sleep", AsyncMock())
    return client, state


def test_client_valid_json(monkeypatch):
    _mock_azure(monkeypatch, '{"copyright": "Copyright (c) 2020 Jane Doe", "reasoning": "ok"}')
    out = asyncio.run(
        Gpt41Client().complete_json("sys", "user")
    )
    assert out["copyright"] == "Copyright (c) 2020 Jane Doe"
    assert out["reasoning"] == "ok"


def test_client_garbage_parse_retry_then_error(monkeypatch):
    client, state = _mock_azure(monkeypatch, ["not-json{{{", "still-bad"])
    with pytest.raises(ParseFailure):
        asyncio.run(Gpt41Client().complete_json("sys", "user"))
    assert state["i"] == 2  # PARSE_ATTEMPTS
    assert client.chat.completions.create.await_count == 2
