import csv
from pathlib import Path

from cache import CachedRecord, read_cache, restore_license_file, write_cache
from input_csv import Component
from pipeline import ComponentResult
from pricing import CallMeta


def _full_result(tmp_path: Path, name: str = "solo@1.0") -> ComponentResult:
    lic = tmp_path / "src_license.txt"
    lic.write_bytes(b"MIT License\nCopyright (c) 2020 Jane Doe\n")
    return ComponentResult(
        component=Component(
            component_name=name,
            purl=f"pkg:npm/{name}",
            lib_name=name.split("@")[0],
            version=name.split("@")[-1],
            slug=name,
            extras={},
        ),
        inferred_license_name="MIT",
        inferred_license_code_url="https://raw.githubusercontent.com/foo/bar/main/LICENSE",
        inferred_copyright="Copyright (c) 2020 Jane Doe",
        license_file_path=lic,
    )


def test_store_round_trip(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    assert write_cache(cache_dir, "solo@1.0", result) is True
    got = read_cache(cache_dir, "solo@1.0")
    assert got is not None
    assert got.inferred_license_name == "MIT"
    assert got.inferred_license_code_url.endswith("/LICENSE")
    assert got.inferred_copyright == "Copyright (c) 2020 Jane Doe"
    assert got.license_path.is_file()
    assert got.license_path.read_bytes() == b"MIT License\nCopyright (c) 2020 Jane Doe\n"


def test_store_unknown_refused(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    result.inferred_copyright = "UNKNOWN"
    assert write_cache(cache_dir, "solo@1.0", result) is False
    assert read_cache(cache_dir, "solo@1.0") is None
    assert not (cache_dir / "cache.csv").exists()


def test_store_none_path_noop(tmp_path):
    result = _full_result(tmp_path)
    assert write_cache(None, "solo@1.0", result) is False
    assert read_cache(None, "solo@1.0") is None


def test_hit_restores_file_into_run_dir(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    write_cache(cache_dir, "solo@1.0", result)
    record = read_cache(cache_dir, "solo@1.0")
    assert isinstance(record, CachedRecord)
    run = tmp_path / "run"
    flat = restore_license_file(record, run, "solo@1.0")
    assert flat == run / "licenses" / "solo@1.0.txt"
    assert flat.is_file()
    assert (run / "per_component" / "solo@1.0" / "solo@1.0.txt").is_file()
    assert flat.read_bytes() == record.license_path.read_bytes()


def test_store_writes_historical_cost_from_metas(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    result.license_meta = CallMeta(known_usd=0.01, billable_calls=1)
    result.copyright_meta = CallMeta(known_usd=0.02, billable_calls=1)
    assert write_cache(cache_dir, "solo@1.0", result) is True
    with (cache_dir / "cache.csv").open(newline="", encoding="utf-8-sig") as f:
        row = next(csv.DictReader(f))
    assert row["cached_historical_cost_usd"] == "0.030000"


def test_store_writes_unknown_historical_cost_when_meta_missing(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    result.copyright_meta = CallMeta(unknown_calls=1)
    assert write_cache(cache_dir, "solo@1.0", result) is True
    with (cache_dir / "cache.csv").open(newline="", encoding="utf-8-sig") as f:
        row = next(csv.DictReader(f))
    assert row["cached_historical_cost_usd"] == "unknown"


def test_read_returns_historical_cost_written_by_write_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    result.license_meta = CallMeta(known_usd=0.05, billable_calls=1)
    write_cache(cache_dir, "solo@1.0", result)
    got = read_cache(cache_dir, "solo@1.0")
    assert got is not None
    assert got.cached_historical_cost == "0.050000"


def test_read_old_index_without_historical_cost_column_still_hits(tmp_path):
    cache_dir = tmp_path / "cache"
    result = _full_result(tmp_path)
    write_cache(cache_dir, "solo@1.0", result)
    index_path = cache_dir / "cache.csv"
    with index_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        old_fieldnames = [c for c in rows[0].keys() if c != "cached_historical_cost_usd"]
    with index_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=old_fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row[c] for c in old_fieldnames})
    got = read_cache(cache_dir, "solo@1.0")
    assert got is not None
    assert got.cached_historical_cost == ""


def test_store_distinct_keys_keep_distinct_files(tmp_path):
    """Same slug basename must not overwrite another component_name's file."""
    cache_dir = tmp_path / "cache"
    a_dir = tmp_path / "a"
    a_dir.mkdir()
    a = _full_result(a_dir, "foo/bar@1")
    a.license_file_path.write_bytes(b"body-a\n")
    # Force identical basename as if both runs used slug foo_bar@1.txt
    a.license_file_path = a.license_file_path.rename(a_dir / "foo_bar@1.txt")
    b_dir = tmp_path / "b"
    b_dir.mkdir()
    b_lic = b_dir / "foo_bar@1.txt"
    b_lic.write_bytes(b"body-b\n")
    b = _full_result(b_dir, "foo_bar@1")
    b.license_file_path = b_lic
    assert write_cache(cache_dir, "foo/bar@1", a)
    assert write_cache(cache_dir, "foo_bar@1", b)
    assert read_cache(cache_dir, "foo/bar@1").license_path.read_bytes() == b"body-a\n"
    assert read_cache(cache_dir, "foo_bar@1").license_path.read_bytes() == b"body-b\n"
