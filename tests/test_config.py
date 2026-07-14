import json
from pathlib import Path

import pytest

import config


def _write_cfg(tmp_path: Path, **overrides) -> Path:
    data = {
        "input_file_path": "input/GT_dedup_with_purl1.csv",
        "output_base_path": "runs",
        "run_name": None,
        "model": "claude-opus-4-8",
        "workers": 20,
        "cache_read": None,
        "cache_write": "caches",
    }
    data.update(overrides)
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_default_json():
    cfg = config.load_config("configs/default.json")
    assert isinstance(cfg.input_file_path, Path)
    assert isinstance(cfg.output_base_path, Path)
    assert isinstance(cfg.model, str) and cfg.model
    assert isinstance(cfg.workers, int)
    assert cfg.run_name is None or isinstance(cfg.run_name, str)
    assert cfg.cache_read is None or isinstance(cfg.cache_read, Path)
    assert cfg.cache_write is None or isinstance(cfg.cache_write, Path)


def test_unknown_model_exits(tmp_path):
    path = _write_cfg(tmp_path, model="not-a-real-model")
    with pytest.raises(SystemExit, match="unknown model"):
        config.load_config(path)


def test_workers_zero_exits(tmp_path):
    path = _write_cfg(tmp_path, workers=0)
    with pytest.raises(SystemExit, match="workers"):
        config.load_config(path)


def test_workers_31_exits(tmp_path):
    path = _write_cfg(tmp_path, workers=31)
    with pytest.raises(SystemExit, match="workers"):
        config.load_config(path)


def test_run_name_null_is_none(tmp_path):
    path = _write_cfg(tmp_path, run_name=None)
    assert config.load_config(path).run_name is None


def test_cache_read_empty_is_none(tmp_path):
    path = _write_cfg(tmp_path, cache_read="")
    assert config.load_config(path).cache_read is None
