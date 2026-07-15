import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import claude_client


def _proc(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


def test_valid_structured_output(monkeypatch):
    payload = {
        "license_name": "MIT",
        "license_code_url": "https://raw.githubusercontent.com/x/y/v1/LICENSE",
        "reasoning": "deps.dev + raw LICENSE",
    }
    wrapper = json.dumps(
        {"structured_output": payload, "total_cost_usd": 0.0042}
    ).encode()

    async def fake_exec(*_a, **_k):
        return _proc(stdout=wrapper)

    monkeypatch.setattr(claude_client.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_client.asyncio, "sleep", AsyncMock())

    out, meta = asyncio.run(
        claude_client.infer_license("pkg:npm/foo@1.0.0", "foo", "1.0.0", "claude-haiku-4-5")
    )
    assert out["license_name"] == "MIT"
    assert out["license_code_url"].endswith("/LICENSE")
    assert "deps.dev" in out["reasoning"]
    assert out["attempts"] == 1
    assert meta.billable_calls == 1
    assert meta.total_usd() == 0.0042
    assert meta.raws[0]


def test_result_string_fallback(monkeypatch):
    inner = {
        "license_name": "Apache-2.0",
        "license_code_url": "",
        "reasoning": "registry only",
    }
    wrapper = json.dumps({"result": json.dumps(inner)}).encode()

    async def fake_exec(*_a, **_k):
        return _proc(stdout=wrapper)

    monkeypatch.setattr(claude_client.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_client.asyncio, "sleep", AsyncMock())

    out, meta = asyncio.run(
        claude_client.infer_license("pkg:npm/bar@2", "bar", "2", "claude-haiku-4-5")
    )
    assert out["license_name"] == "Apache-2.0"
    assert out["license_code_url"] == ""
    assert meta.billable_calls == 1
    assert meta.total_usd() is None  # no total_cost_usd on wrapper


def test_garbage_json_unknown_after_parse_retries(monkeypatch):
    calls = {"n": 0}

    async def fake_exec(*_a, **_k):
        calls["n"] += 1
        return _proc(stdout=b"not-json{{{")

    monkeypatch.setattr(claude_client.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_client.asyncio, "sleep", AsyncMock())

    out, meta = asyncio.run(
        claude_client.infer_license("pkg:npm/x@1", "x", "1", "claude-haiku-4-5")
    )
    assert out["license_name"] == "UNKNOWN"
    assert out["license_code_url"] == ""
    assert calls["n"] == 2
    assert out["attempts"] == 2
    assert meta.billable_calls == 2
    assert meta.unknown_calls == 2


def test_nonzero_exit_transient_then_unknown(monkeypatch):
    calls = {"n": 0}

    async def fake_exec(*_a, **_k):
        calls["n"] += 1
        return _proc(stderr=b"timeout", returncode=1)

    monkeypatch.setattr(claude_client.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_client.asyncio, "sleep", AsyncMock())

    out, meta = asyncio.run(
        claude_client.infer_license("pkg:npm/x@1", "x", "1", "claude-haiku-4-5")
    )
    assert out["license_name"] == "UNKNOWN"
    assert calls["n"] == 3
    assert out["attempts"] == 3
    assert meta.billable_calls == 0  # non-zero exit: no billable response


def test_hard_4xx_no_retry(monkeypatch):
    calls = {"n": 0}

    async def fake_exec(*_a, **_k):
        calls["n"] += 1
        return _proc(stderr=b"HTTP 401 unauthorized", returncode=1)

    monkeypatch.setattr(claude_client.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_client.asyncio, "sleep", AsyncMock())

    out, meta = asyncio.run(
        claude_client.infer_license("pkg:npm/x@1", "x", "1", "claude-haiku-4-5")
    )
    assert out["license_name"] == "UNKNOWN"
    assert calls["n"] == 1
    assert "hard failure" in out["reasoning"]
    assert meta.billable_calls == 0


def test_parse_reject_then_good_sums_cost(monkeypatch):
    """Valid wrapper + broken payload, then good retry → 2 billable, cost summed."""
    bad_payload = {"license_name": "MIT"}  # missing keys
    good_payload = {
        "license_name": "MIT",
        "license_code_url": "https://example.com/LICENSE",
        "reasoning": "ok",
    }
    responses = [
        json.dumps({"structured_output": bad_payload, "total_cost_usd": 0.01}).encode(),
        json.dumps({"structured_output": good_payload, "total_cost_usd": 0.02}).encode(),
    ]
    calls = {"n": 0}

    async def fake_exec(*_a, **_k):
        i = calls["n"]
        calls["n"] += 1
        return _proc(stdout=responses[i])

    monkeypatch.setattr(claude_client.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(claude_client.asyncio, "sleep", AsyncMock())

    out, meta = asyncio.run(
        claude_client.infer_license("pkg:npm/x@1", "x", "1", "claude-haiku-4-5")
    )
    assert out["license_name"] == "MIT"
    assert out["attempts"] == 2
    assert meta.billable_calls == 2
    assert meta.total_usd() == 0.03
    assert len(meta.raws) == 2
