import asyncio

import pytest

import retry


class TransientErr(Exception):
    pass


class ParseErr(Exception):
    pass


class HardErr(Exception):
    pass


def _classify(exc: BaseException) -> str:
    if isinstance(exc, TransientErr):
        return "transient"
    if isinstance(exc, ParseErr):
        return "parse"
    if isinstance(exc, HardErr):
        return "hard"
    raise AssertionError(f"unexpected: {exc!r}")


def test_transient_retries_then_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(retry.random, "uniform", lambda a, b: 5.0)

    n = {"calls": 0}

    async def flaky():
        n["calls"] += 1
        if n["calls"] < 3:
            raise TransientErr("boom")
        return "ok"

    assert asyncio.run(retry.with_retries(flaky, classify=_classify)) == "ok"
    assert n["calls"] == 3
    assert sleeps == [2.0, 5.0]


def test_transient_exhausts_after_three(monkeypatch):
    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(retry.random, "uniform", lambda a, b: 4.0)

    n = {"calls": 0}

    async def always():
        n["calls"] += 1
        raise TransientErr("nope")

    with pytest.raises(TransientErr):
        asyncio.run(retry.with_retries(always, classify=_classify))
    assert n["calls"] == 3


def test_parse_retries_once_then_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)

    n = {"calls": 0}

    async def flaky():
        n["calls"] += 1
        if n["calls"] == 1:
            raise ParseErr("bad json")
        return {"license_name": "MIT"}

    assert asyncio.run(retry.with_retries(flaky, classify=_classify)) == {
        "license_name": "MIT"
    }
    assert n["calls"] == 2
    assert sleeps == [1.0]


def test_parse_exhausts_after_two(monkeypatch):
    async def fake_sleep(_s):
        return None

    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)

    n = {"calls": 0}

    async def always():
        n["calls"] += 1
        raise ParseErr("still bad")

    with pytest.raises(ParseErr):
        asyncio.run(retry.with_retries(always, classify=_classify))
    assert n["calls"] == 2


def test_hard_failure_no_retry(monkeypatch):
    slept = {"n": 0}

    async def track_sleep(_s):
        slept["n"] += 1

    monkeypatch.setattr(retry.asyncio, "sleep", track_sleep)

    n = {"calls": 0}

    async def once():
        n["calls"] += 1
        raise HardErr("401")

    with pytest.raises(HardErr):
        asyncio.run(retry.with_retries(once, classify=_classify))
    assert n["calls"] == 1
    assert slept["n"] == 0
