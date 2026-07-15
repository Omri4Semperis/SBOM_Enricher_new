import asyncio
from unittest.mock import AsyncMock, MagicMock

import gpt41_client
import pytest
import retry
from gpt41_client import Gpt41Client, ParseFailure
from pricing import CallMeta


def _mock_azure(monkeypatch, content: str | list[str], *, usage=None):
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
        resp.usage = usage
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
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    usage.prompt_tokens_details = None
    _mock_azure(
        monkeypatch,
        '{"copyright": "Copyright (c) 2020 Jane Doe", "reasoning": "ok"}',
        usage=usage,
    )
    out, meta = asyncio.run(Gpt41Client().complete_json("sys", "user"))
    assert out["copyright"] == "Copyright (c) 2020 Jane Doe"
    assert out["reasoning"] == "ok"
    assert meta.billable_calls == 1
    assert meta.cost_cell() != "unknown"
    assert meta.raws[0]


def test_client_garbage_parse_retry_then_error(monkeypatch):
    client, state = _mock_azure(monkeypatch, ["not-json{{{", "still-bad"])
    with pytest.raises(ParseFailure):
        asyncio.run(Gpt41Client().complete_json("sys", "user"))
    assert state["i"] == 2  # PARSE_ATTEMPTS
    assert client.chat.completions.create.await_count == 2


MIT_LICENSE = """\
MIT License

Copyright (c) 2020 Jane Doe

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.
"""


def test_extract_verbatim_from_fixture(monkeypatch):
    async def fake_complete(self, system, user):
        assert "Jane Doe" in user
        meta = CallMeta()
        meta.add_call(cost_usd=0.001, raw='{"copyright":"Copyright (c) 2020 Jane Doe"}')
        return {
            "copyright": "Copyright (c) 2020 Jane Doe",
            "reasoning": "found notice line",
        }, meta

    monkeypatch.setattr(Gpt41Client, "complete_json", fake_complete)
    import copyright as copyright_mod

    out, meta = asyncio.run(copyright_mod.extract_copyright(MIT_LICENSE))
    assert out["copyright"] == "Copyright (c) 2020 Jane Doe"
    assert "notice" in out["reasoning"]
    assert meta.billable_calls == 1
    assert meta.cost_cell() == "0.001000"


def test_extract_placeholder_unknown(monkeypatch):
    async def fake_complete(self, system, user):
        meta = CallMeta()
        meta.add_call(cost_usd=0.0001, raw="{}")
        return {
            "copyright": "Copyright (c) <year> <copyright holders>",
            "reasoning": "template line",
        }, meta

    monkeypatch.setattr(Gpt41Client, "complete_json", fake_complete)
    import copyright as copyright_mod

    out, meta = asyncio.run(
        copyright_mod.extract_copyright("MIT License\nCopyright (c) <year>")
    )
    assert out["copyright"] == "UNKNOWN"
    assert "placeholder" in out["reasoning"]
    assert meta.billable_calls == 1


def test_extract_empty_text_no_llm(monkeypatch):
    called = {"n": 0}

    async def fake_complete(self, system, user):
        called["n"] += 1
        return {"copyright": "x", "reasoning": "y"}, CallMeta()

    monkeypatch.setattr(Gpt41Client, "complete_json", fake_complete)
    import copyright as copyright_mod

    out, meta = asyncio.run(copyright_mod.extract_copyright("   "))
    assert out["copyright"] == "UNKNOWN"
    assert called["n"] == 0
    assert meta.billable_calls == 0


def test_extract_unknown_after_parse_retries(monkeypatch):
    async def fake_complete(self, system, user):
        raise ParseFailure("garbage")

    monkeypatch.setattr(Gpt41Client, "complete_json", fake_complete)
    import copyright as copyright_mod

    out, meta = asyncio.run(copyright_mod.extract_copyright(MIT_LICENSE))
    assert out["copyright"] == "UNKNOWN"
    assert "retries exhausted" in out["reasoning"]
    assert meta.billable_calls == 0
