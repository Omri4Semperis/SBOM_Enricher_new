import json
from pathlib import Path

import event_report


def _write(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "events.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def _rec(op, phase, op_id=None, mono=0.0, ts="2026-01-01T00:00:00+00:00", **extra):
    rec = {"ts": ts, "mono": mono, "op": op, "phase": phase}
    if op_id is not None:
        rec["op_id"] = op_id
    rec.update(extra)
    return rec


def _section(report: str, header: str) -> str:
    """Body lines of one ``== header ==`` block, up to the next ``==`` line."""
    lines = report.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(f"== {header}"))
    body = []
    for ln in lines[start + 1 :]:
        if ln.startswith("=="):
            break
        body.append(ln)
    return "\n".join(body)


def test_open_span_is_in_flight_not_in_latency_table():
    """A started-but-never-ended op is invisible to latency, visible in-flight."""
    records = [
        _rec("run", "start", mono=0.0, run_id="r1", components=1, model="m", workers=1),
        _rec("claude", "start", op_id=1, mono=10.0, slug="pkg@1.0", stage="license"),
        _rec("download", "start", op_id=2, mono=15.0, slug="other@1.0"),
        _rec("download", "end", op_id=2, mono=16.0, dur_s=1.0, status="ok", slug="other@1.0"),
        _rec("row_written", "event", mono=20.0),
    ]
    data = event_report._load_from_records(records)
    assert data["now_mono"] == 20.0
    assert len(data["open"]) == 1
    open_span = data["open"][0]
    assert open_span["op"] == "claude"
    assert open_span["slug"] == "pkg@1.0"
    assert open_span["dur_s"] is None

    report = event_report._report(data, top=10, only_op=None, tail_over=None)
    assert "status: IN FLIGHT" in report
    assert "== in-flight" in report
    assert "10.0s  claude" in report
    assert "pkg@1.0" in report
    # The open op never got a dur_s, so it must not pollute per-op latency.
    latency_section = _section(report, "per-op latency")
    assert "claude" not in latency_section


def test_no_open_spans_reports_none():
    records = [
        _rec("run", "start", mono=0.0, run_id="r1", components=1, model="m", workers=1),
        _rec("run", "end", mono=5.0, dur_s=5.0),
    ]
    data = event_report._load_from_records(records)
    report = event_report._report(data, top=10, only_op=None, tail_over=None)
    assert "status: COMPLETE" in report
    assert _section(report, "in-flight").strip() == "none"


def test_tail_over_tags_open_span_and_includes_it():
    records = [
        _rec("component", "start", op_id=1, mono=0.0, slug="slow@1.0"),
        _rec("component", "start", op_id=2, mono=90.0, slug="fresh@1.0"),
        _rec("row_written", "event", mono=100.0),
    ]
    data = event_report._load_from_records(records)
    report = event_report._report(data, top=10, only_op=None, tail_over=50.0)
    tail_section = _section(report, "spans/open-ops")
    assert "slow@1.0" in tail_section
    assert "[OPEN]" in tail_section
    # fresh@1.0 is only 10s old (< 50s threshold) -> excluded.
    assert "fresh@1.0" not in tail_section


def test_concurrency_counts_open_component_span():
    records = [
        _rec("component", "start", op_id=1, mono=0.0, slug="a@1.0"),
        _rec("component", "end", op_id=1, mono=10.0, dur_s=10.0, status="ok", slug="a@1.0"),
        _rec("component", "start", op_id=2, mono=5.0, slug="b@1.0"),
        _rec("row_written", "event", mono=20.0),
    ]
    data = event_report._load_from_records(records)
    report = event_report._report(data, top=10, only_op=None, tail_over=None)
    concurrency_line = _section(report, "concurrency")
    assert "peak=2" in concurrency_line
    assert "incl. 1 still-open" in concurrency_line


def test_torn_last_line_is_tolerated(tmp_path):
    path = tmp_path / "events.jsonl"
    good = json.dumps(_rec("claude", "start", op_id=1, mono=0.0, slug="a@1.0"))
    with path.open("w", encoding="utf-8") as f:
        f.write(good + "\n")
        f.write('{"op": "claude", "phase": "end", "op_id": 1, "mo')  # torn write
    data = event_report._load(path)
    assert data["lines"] == 1
    assert len(data["open"]) == 1


def test_main_prints_in_flight_section(tmp_path, capsys):
    records = [
        _rec("run", "start", mono=0.0, run_id="r1", components=1, model="m", workers=1),
        _rec("claude", "start", op_id=1, mono=0.0, slug="a@1.0"),
        _rec("row_written", "event", mono=30.0),
    ]
    path = _write(tmp_path, records)
    rc = event_report.main([str(path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "IN FLIGHT" in out
    assert "== in-flight" in out
    assert "a@1.0" in out
