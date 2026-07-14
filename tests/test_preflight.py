from unittest.mock import MagicMock

import pytest

import config
import preflight


def _cfg() -> config.Config:
    return config.Config(
        input_file_path=MagicMock(),
        output_base_path=MagicMock(),
        run_name=None,
        model="claude-haiku-4-5",
        workers=1,
        cache_read=None,
        cache_write=None,
    )


def test_preflight_success(monkeypatch):
    monkeypatch.setattr(preflight, "_probe_claude", lambda model: None)
    monkeypatch.setattr(preflight, "_probe_azure", lambda: None)
    slept = []
    monkeypatch.setattr(preflight.time, "sleep", slept.append)
    preflight.preflight(_cfg())
    assert slept == []


def test_preflight_claude_fails_after_retries(monkeypatch):
    calls = {"n": 0}

    def boom(model):
        calls["n"] += 1
        raise RuntimeError("claude down")

    monkeypatch.setattr(preflight, "_probe_claude", boom)
    monkeypatch.setattr(preflight, "_probe_azure", lambda: None)
    slept = []
    monkeypatch.setattr(preflight.time, "sleep", slept.append)
    with pytest.raises(SystemExit, match="Preflight failed \\(claude\\)"):
        preflight.preflight(_cfg())
    assert calls["n"] == preflight.ATTEMPTS
    assert slept == list(preflight.BACKOFFS[: preflight.ATTEMPTS - 1])


def test_preflight_azure_fails_after_retries(monkeypatch):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("azure down")

    monkeypatch.setattr(preflight, "_probe_claude", lambda model: None)
    monkeypatch.setattr(preflight, "_probe_azure", boom)
    slept = []
    monkeypatch.setattr(preflight.time, "sleep", slept.append)
    with pytest.raises(SystemExit, match="Preflight failed \\(azure\\)"):
        preflight.preflight(_cfg())
    assert calls["n"] == preflight.ATTEMPTS
    assert slept == list(preflight.BACKOFFS[: preflight.ATTEMPTS - 1])


def test_preflight_recovers_on_second_attempt(monkeypatch):
    state = {"n": 0}

    def flaky(model):
        state["n"] += 1
        if state["n"] < 2:
            raise RuntimeError("blip")

    monkeypatch.setattr(preflight, "_probe_claude", flaky)
    monkeypatch.setattr(preflight, "_probe_azure", lambda: None)
    slept = []
    monkeypatch.setattr(preflight.time, "sleep", slept.append)
    preflight.preflight(_cfg())
    assert state["n"] == 2
    assert slept == [2.0]
