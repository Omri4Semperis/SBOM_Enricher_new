"""Prompt-string checks (offline; no model calls)."""

from prompts import license_prompt


def test_license_prompt_url_guidance():
    text, _schema = license_prompt("pkg:generic/nettle@3.9", "nettle", "3.9")
    lower = text.casefold()
    assert "holder" in lower
    assert "boilerplate" in lower or "canonical" in lower
    assert "authors" in lower
    assert "notice" in lower
    assert "raw" in lower
    assert "main/master/head" in lower
