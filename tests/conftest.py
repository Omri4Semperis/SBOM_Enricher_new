import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(autouse=True)
def _noop_preflight(monkeypatch):
    """Suite never hits live providers; P8 preflight is mocked everywhere."""
    monkeypatch.setattr("main.preflight", lambda config: None)
