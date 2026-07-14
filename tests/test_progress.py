from progress import Progress, format_eta, progress_bar, render_line


def test_bar_empty_mid_done():
    assert progress_bar(0, 10) == "[" + "░" * 35 + "] 0/10"
    mid = progress_bar(5, 10)
    assert mid.startswith("[") and mid.endswith("] 5/10")
    assert "█" in mid and "░" in mid
    assert progress_bar(10, 10) == "[" + "█" * 35 + "] 10/10"
    assert progress_bar(0, 0) == "[" + "░" * 35 + "] 0/0"


def test_eta_formatting():
    assert format_eta(0, 10, 0.0) == "ETA --"
    assert format_eta(5, 10, 10.0) == "ETA 10s"
    assert format_eta(10, 10, 7.0) == "done in 7s"


def test_render_line_includes_bar_and_eta():
    line = render_line(2, 4, 4.0)
    assert "[█" in line or "[░" in line
    assert "2/4" in line
    assert "ETA" in line


def test_render_line_pads_eta_against_stale_chars():
    # Trailing pad after ETA keeps line length stable as ETA digits shrink.
    short_eta = render_line(9, 10, 180.0)  # ~ETA 20s
    long_eta = render_line(9, 10, 900.0)  # ~ETA 100s
    assert len(short_eta) == len(long_eta)
    assert format_eta(9, 10, 180.0) in short_eta
    assert short_eta.endswith(" ")


def test_progress_tick(monkeypatch):
    lines = []
    monkeypatch.setattr(
        "builtins.print",
        lambda *a, **k: lines.append(a[0] if a else ""),
    )
    p = Progress(2)
    p.start()
    p.tick()
    p.tick()
    assert p.done == 2
    assert any("1/2" in str(x) for x in lines)
    assert any("2/2" in str(x) for x in lines)
