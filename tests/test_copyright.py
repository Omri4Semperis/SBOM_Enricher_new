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


def test_client_empty_choices_still_billed(monkeypatch):
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 0
    usage.prompt_tokens_details = None
    client, _state = _mock_azure(monkeypatch, "ignored", usage=usage)

    async def create(**_kwargs):
        resp = MagicMock()
        resp.choices = []
        resp.usage = usage
        return resp

    client.chat.completions.create = AsyncMock(side_effect=create)
    with pytest.raises(ParseFailure) as ei:
        asyncio.run(Gpt41Client().complete_json("sys", "user"))
    assert ei.value.meta.billable_calls >= 1
    assert ei.value.meta.cost_cell() != "unknown"


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


def test_npm_author_strips_email_and_url(monkeypatch):
    import copyright as copyright_mod

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"author": "Jane Doe <jane@example.com> (https://jane.dev)"}

    monkeypatch.setattr(
        copyright_mod.requests, "get", lambda *_a, **_k: Resp()
    )
    assert (
        copyright_mod._npm_author_copyright("pkg:npm/foo@1.0.0")
        == "Copyright (c) Jane Doe"
    )


def test_npm_author_object_name(monkeypatch):
    import copyright as copyright_mod

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"author": {"name": "Acme Inc", "email": "a@acme.com"}}

    monkeypatch.setattr(
        copyright_mod.requests, "get", lambda *_a, **_k: Resp()
    )
    assert (
        copyright_mod._npm_author_copyright("pkg:npm/foo@1.0.0")
        == "Copyright (c) Acme Inc"
    )


def test_npm_author_ignores_contributors_and_maintainers(monkeypatch):
    import copyright as copyright_mod

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "contributors": [{"name": "Contrib"}],
                "maintainers": [{"name": "Maint"}],
            }

    monkeypatch.setattr(
        copyright_mod.requests, "get", lambda *_a, **_k: Resp()
    )
    assert copyright_mod._npm_author_copyright("pkg:npm/foo@1.0.0") is None


def test_npm_author_non_npm_purl():
    import copyright as copyright_mod

    assert copyright_mod._npm_author_copyright("pkg:pypi/foo@1") is None


def test_resolve_file_success_skips_fallbacks(monkeypatch):
    import copyright as copyright_mod

    async def fake_extract(text):
        meta = CallMeta()
        meta.add_call(cost_usd=0.001, raw="{}")
        return {"copyright": "Copyright (c) File", "reasoning": "from file"}, meta

    called = {"npm": 0, "web": 0}

    def fake_npm(_purl):
        called["npm"] += 1
        return "Copyright (c) Npm"

    async def fake_web(*_a, **_k):
        called["web"] += 1
        return {"copyright": "Copyright (c) Web", "reasoning": "web"}, CallMeta()

    monkeypatch.setattr(copyright_mod, "extract_copyright", fake_extract)
    monkeypatch.setattr(copyright_mod, "_npm_author_copyright", fake_npm)
    monkeypatch.setattr(copyright_mod, "infer_copyright_web", fake_web)

    out, meta = asyncio.run(
        copyright_mod.resolve_copyright(
            MIT_LICENSE, "pkg:npm/foo@1", "foo", "1", "claude-haiku-4-5"
        )
    )
    assert out["copyright"] == "Copyright (c) File"
    assert called == {"npm": 0, "web": 0}
    assert meta.billable_calls == 1


def test_resolve_npm_when_file_unknown(monkeypatch):
    import copyright as copyright_mod

    async def fake_extract(text):
        return copyright_mod._unknown("empty license text"), CallMeta()

    called = {"web": 0}

    def fake_npm(_purl):
        return "Copyright (c) Npm Author"

    async def fake_web(*_a, **_k):
        called["web"] += 1
        return {"copyright": "Copyright (c) Web", "reasoning": "web"}, CallMeta()

    monkeypatch.setattr(copyright_mod, "extract_copyright", fake_extract)
    monkeypatch.setattr(copyright_mod, "_npm_author_copyright", fake_npm)
    monkeypatch.setattr(copyright_mod, "infer_copyright_web", fake_web)

    out, meta = asyncio.run(
        copyright_mod.resolve_copyright(
            "", "pkg:npm/foo@1", "foo", "1", "claude-haiku-4-5"
        )
    )
    assert out["copyright"] == "Copyright (c) Npm Author"
    assert out["reasoning"] == "npm_author"
    assert called["web"] == 0
    assert meta.billable_calls == 0


def test_resolve_web_when_file_and_npm_unknown(monkeypatch):
    import copyright as copyright_mod

    async def fake_extract(text):
        file_meta = CallMeta()
        file_meta.add_call(cost_usd=0.002, raw="file")
        return copyright_mod._unknown("no notice"), file_meta

    def fake_npm(_purl):
        return None

    async def fake_web(*_a, **_k):
        web_meta = CallMeta()
        web_meta.add_call(cost_usd=0.005, raw="web")
        return {
            "copyright": "Copyright (c) Web Holder",
            "reasoning": "upstream NOTICE",
        }, web_meta

    monkeypatch.setattr(copyright_mod, "extract_copyright", fake_extract)
    monkeypatch.setattr(copyright_mod, "_npm_author_copyright", fake_npm)
    monkeypatch.setattr(copyright_mod, "infer_copyright_web", fake_web)

    out, meta = asyncio.run(
        copyright_mod.resolve_copyright(
            MIT_LICENSE, "pkg:npm/foo@1", "foo", "1", "claude-haiku-4-5"
        )
    )
    assert out["copyright"] == "Copyright (c) Web Holder"
    assert out["reasoning"].startswith("web:")
    assert meta.billable_calls == 2
    assert meta.total_usd() == 0.007


def test_resolve_web_placeholder_rejected(monkeypatch):
    import copyright as copyright_mod

    async def fake_extract(text):
        return copyright_mod._unknown("empty"), CallMeta()

    monkeypatch.setattr(copyright_mod, "extract_copyright", fake_extract)
    monkeypatch.setattr(copyright_mod, "_npm_author_copyright", lambda _p: None)

    async def fake_web(*_a, **_k):
        meta = CallMeta()
        meta.add_call(cost_usd=0.001, raw="{}")
        return {
            "copyright": "Copyright (c) <year> <copyright holders>",
            "reasoning": "template",
        }, meta

    monkeypatch.setattr(copyright_mod, "infer_copyright_web", fake_web)

    out, meta = asyncio.run(
        copyright_mod.resolve_copyright(
            "", "pkg:npm/foo@1", "foo", "1", "claude-haiku-4-5"
        )
    )
    assert out["copyright"] == "UNKNOWN"
    assert "placeholder" in out["reasoning"]
    assert meta.billable_calls == 1
