#!/usr/bin/env python3
"""Generate a self-contained HTML run-time / accuracy report for a run dir.

Reads what the app already writes — `summary.json` for run-level facts, each
`per_component/{slug}/story.txt` for per-phase durations, and (in audit mode)
`results_*_extended.csv` for Hit/Mismatch grades — and renders a single
standalone HTML file (no external assets, works offline).

Called automatically at the end of an enrichment run (`main.run`). Also
standalone-runnable against any existing run directory:

    .\\.venv\\Scripts\\python.exe src\\runtime_report.py runs\\20260715_135507_ClaudeOpu-4-8_10
    .\\.venv\\Scripts\\python.exe src\\runtime_report.py <run_dir> --out report.html --open

Only the Python standard library is used. Timings come from the Story lines
(`timing_s=`), which the app treats as the source of truth for post-hoc
timings. Equality-judge calls are not timed by the app, so they appear in the
run's wall clock but not in the per-phase compute totals (surfaced as a note).
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
import sys
import webbrowser
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

csv.field_size_limit(10_000_000)  # extended CSV carries big raw-response cells

# Phases the Story records a `timing_s=` for, in pipeline order. The label and
# color are shared by every chart/table so the report reads consistently.
PHASES: tuple[tuple[str, str, str], ...] = (
    ("license", "License inference", "#6366f1"),   # Claude CLI subprocess
    ("download", "License download", "#f59e0b"),    # HTTP fetch
    ("copyright", "Copyright extraction", "#14b8a6"),  # GPT-4.1 call
)
PHASE_KEYS = tuple(p[0] for p in PHASES)
PHASE_LABEL = {p[0]: p[1] for p in PHASES}
PHASE_COLOR = {p[0]: p[2] for p in PHASES}
CACHE_COLOR = "#94a3b8"

# Audit-mode accuracy grades (from the extended CSV `grades` column) and the
# ground-truth fields they apply to. Hit-rate excludes Unscoreable from the
# denominator (matches src/scoring.py + the run's DECISIONS G2).
#
# Colors are the Okabe-Ito colorblind-safe palette, deliberately NOT
# green-vs-red for Hit-vs-Mismatch (that pair is the one most CVD types
# confuse). Blue vs. vermillion stays distinguishable under protanopia,
# deuteranopia, and tritanopia. Every use also carries a glyph (see
# GRADE_GLYPH) so no signal is color-only.
GRADES: tuple[tuple[str, str, str], ...] = (
    ("Hit", "#0072B2", "\u2713"),  # blue, check
    ("Mismatch", "#D55E00", "\u2717"),  # vermillion, cross
    ("Unknown", "#767676", "?"),  # neutral gray
    ("Unscoreable", "#CC79A7", "\u2014"),  # reddish purple, dash
)
GRADE_ORDER = tuple(g[0] for g in GRADES)
GRADE_COLOR = {g[0]: g[1] for g in GRADES}
GRADE_GLYPH = {g[0]: g[2] for g in GRADES}
GT_FIELDS = ("license_name", "license_code_url", "copyright")
FIELD_LABEL = {
    "license_name": "License name",
    "license_code_url": "License URL",
    "copyright": "Copyright",
}
EQ_REASON_COL = {
    "license_name": "eq_license_name_reason",
    "license_code_url": "eq_license_code_url_reason",
    "copyright": "eq_copyright_reason",
}

# Only the final download line carries a timing_s; matches summary.py semantics.
_TIMING_RE = re.compile(
    r"^(license|download|copyright):.*?\btiming_s=([0-9.]+)", re.MULTILINE
)
_ATTEMPTS_RE = re.compile(r"^license:.*?\battempts=(\S+)", re.MULTILINE)
_LICENSE_REASON_RE = re.compile(r"^license:\s+(.*?)\s+attempts=", re.MULTILINE)
_COPYRIGHT_REASON_RE = re.compile(r"^copyright:\s+(.*?)\s+timing_s=", re.MULTILINE)
_DL_OUTCOME_RE = re.compile(r"^download:\s+(chose|failed)\b(.*)$", re.MULTILINE)


@dataclass
class Component:
    slug: str
    name: str
    purl: str
    from_cache: bool = False
    timings: dict[str, float] = field(default_factory=dict)  # phase -> seconds
    license_attempts: str = ""
    license_reason: str = ""
    copyright_reason: str = ""
    download_outcome: str = ""  # "chose ..." / "failed (...)" / ""
    grades: dict[str, str] = field(default_factory=dict)  # gt field -> grade
    eq_reasons: dict[str, str] = field(default_factory=dict)  # gt field -> reason

    @property
    def total(self) -> float:
        return sum(self.timings.values())


@dataclass
class AuditData:
    """Per-field accuracy pulled from the extended CSV `grades` column.

    `fields` is the subset of GT_FIELDS actually graded in this run (a run may
    carry ground truth for only some fields).
    """

    fields: list[str]
    counts: dict[str, Counter]  # field -> Counter[grade]
    mismatch_reasons: dict[str, Counter]  # field -> Counter[reason bucket]
    mismatch_ecosystems: dict[str, Counter]  # field -> Counter[ecosystem]
    n_rows: int

    def hit_rate(self, field_name: str) -> float | None:
        c = self.counts[field_name]
        scoreable = c["Hit"] + c["Mismatch"] + c["Unknown"]
        return (c["Hit"] / scoreable) if scoreable else None


@dataclass
class RunData:
    run_dir: Path
    run_id: str
    summary: dict | None
    components: list[Component]
    audit: AuditData | None = None

    # --- run-level facts (fall back gracefully when summary.json is absent) ---
    @property
    def info(self) -> dict:
        return (self.summary or {}).get("run_info", {})

    @property
    def wall_seconds(self) -> float | None:
        t = (self.summary or {}).get("timings", {})
        return t.get("wall_seconds")

    @property
    def total_cost(self) -> str | None:
        return (self.summary or {}).get("costs", {}).get("total_usd")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def parse_component(comp_dir: Path) -> Component | None:
    """A real component dir has a story.txt; `__eq_*` helper dirs do not."""
    story_path = comp_dir / "story.txt"
    if not story_path.is_file():
        return None
    story = story_path.read_text(encoding="utf-8", errors="replace")

    meta = _read_json(comp_dir / "meta.json") or {}
    comp = Component(
        slug=comp_dir.name,
        name=meta.get("component_name") or comp_dir.name,
        purl=meta.get("purl", ""),
    )

    if "cache hit" in story:
        comp.from_cache = True

    for kind, val in _TIMING_RE.findall(story):
        try:
            comp.timings[kind] = float(val)
        except ValueError:
            pass

    m = _ATTEMPTS_RE.search(story)
    if m:
        comp.license_attempts = m.group(1)
    m = _LICENSE_REASON_RE.search(story)
    if m:
        comp.license_reason = m.group(1).strip()
    m = _COPYRIGHT_REASON_RE.search(story)
    if m:
        comp.copyright_reason = m.group(1).strip()
    m = _DL_OUTCOME_RE.search(story)
    if m:
        comp.download_outcome = (m.group(1) + m.group(2)).strip()

    return comp


def _extended_csv(run_dir: Path) -> Path | None:
    matches = sorted(run_dir.glob("results_*_extended.csv"))
    return matches[0] if matches else None


def _ecosystem(purl: str) -> str:
    m = re.match(r"pkg:([^/]+)/", (purl or "").strip())
    return m.group(1).lower() if m else "(none)"


def _reason_bucket(reason: str) -> str:
    """Collapse an equality reason into a root-cause bucket (see analyze_run.py)."""
    r = (reason or "").strip()
    if not r:
        return "(empty)"
    if r.startswith("judge:"):
        return "judge: content differs"
    if r.startswith("judge_bad_verdict"):
        return "judge_bad_verdict"
    return r  # ladder reasons: identical / normalized / *_download_failed / ...


def _parse_grades(cell: str) -> dict[str, str]:
    try:
        return json.loads(cell or "{}")
    except json.JSONDecodeError:
        return {}


def load_audit(run_dir: Path, components: list[Component]) -> AuditData | None:
    """Read the extended CSV grades; attach per-component grades by name.

    Returns None when the run has no graded rows (i.e. not an audit run).
    """
    path = _extended_csv(run_dir)
    if path is None or not path.is_file():
        return None

    by_name: dict[str, Component] = {c.name: c for c in components}
    counts: dict[str, Counter] = {f: Counter() for f in GT_FIELDS}
    mismatch_reasons: dict[str, Counter] = {f: Counter() for f in GT_FIELDS}
    mismatch_ecos: dict[str, Counter] = {f: Counter() for f in GT_FIELDS}
    graded_fields: set[str] = set()
    n_rows = 0

    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            grades = _parse_grades(row.get("grades", ""))
            if not grades:
                continue
            n_rows += 1
            comp = by_name.get(row.get("component_name", ""))
            for gf, grade in grades.items():
                if gf not in counts:
                    continue
                graded_fields.add(gf)
                counts[gf][grade] += 1
                reason = row.get(EQ_REASON_COL[gf], "")
                if comp is not None:
                    comp.grades[gf] = grade
                    comp.eq_reasons[gf] = reason
                if grade == "Mismatch":
                    mismatch_reasons[gf][_reason_bucket(reason)] += 1
                    mismatch_ecos[gf][_ecosystem(row.get("purl", ""))] += 1

    if not graded_fields:
        return None
    fields = [f for f in GT_FIELDS if f in graded_fields]
    return AuditData(
        fields=fields,
        counts=counts,
        mismatch_reasons=mismatch_reasons,
        mismatch_ecosystems=mismatch_ecos,
        n_rows=n_rows,
    )


def load_run(run_dir: Path) -> RunData:
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")
    summary = _read_json(run_dir / "summary.json")
    per_component = run_dir / "per_component"
    components: list[Component] = []
    if per_component.is_dir():
        for comp_dir in sorted(per_component.iterdir()):
            if not comp_dir.is_dir():
                continue
            comp = parse_component(comp_dir)
            if comp is not None:
                components.append(comp)
    audit = load_audit(run_dir, components)
    run_id = summary.get("run_info", {}).get("run_id") if summary else run_dir.name
    return RunData(
        run_dir=run_dir,
        run_id=run_id or run_dir.name,
        summary=summary,
        components=components,
        audit=audit,
    )


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:04.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes:02d}m {secs:04.1f}s"


def fmt_iso(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    except ValueError:
        return iso


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def pct(part: float, whole: float) -> float:
    return (part / whole * 100.0) if whole else 0.0


# --------------------------------------------------------------------------- #
# HTML building blocks
# --------------------------------------------------------------------------- #
def stat_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="card-sub">{esc(sub)}</div>' if sub else ""
    return (
        '<div class="card">'
        f'<div class="card-label">{esc(label)}</div>'
        f'<div class="card-value">{value}</div>'
        f"{sub_html}</div>"
    )


def stacked_bar(segments: list[tuple[str, float, str]], total: float) -> str:
    """segments: (label, value_seconds, color). Renders one flex bar."""
    if total <= 0:
        return '<div class="bar empty"></div>'
    cells = []
    for label, value, color in segments:
        if value <= 0:
            continue
        width = pct(value, total)
        title = f"{label}: {fmt_dur(value)} ({width:.0f}%)"
        cells.append(
            f'<span class="seg" style="width:{width:.4f}%;background:{color}" '
            f'title="{esc(title)}"></span>'
        )
    return f'<div class="bar">{"".join(cells)}</div>'


def legend() -> str:
    items = [
        f'<span class="lg"><i style="background:{color}"></i>{esc(label)}</span>'
        for _, label, color in PHASES
    ]
    items.append(
        f'<span class="lg"><i style="background:{CACHE_COLOR}"></i>Cache hit</span>'
    )
    return f'<div class="legend">{"".join(items)}</div>'


def phase_breakdown_section(run: RunData) -> str:
    totals = {k: 0.0 for k in PHASE_KEYS}
    counts = {k: 0 for k in PHASE_KEYS}
    per_phase_values: dict[str, list[float]] = {k: [] for k in PHASE_KEYS}
    for c in run.components:
        for k in PHASE_KEYS:
            if k in c.timings:
                totals[k] += c.timings[k]
                counts[k] += 1
                per_phase_values[k].append(c.timings[k])
    grand = sum(totals.values())

    bar = stacked_bar(
        [(PHASE_LABEL[k], totals[k], PHASE_COLOR[k]) for k in PHASE_KEYS], grand
    )

    rows = []
    for k in PHASE_KEYS:
        vals = per_phase_values[k]
        avg = statistics.mean(vals) if vals else None
        mx = max(vals) if vals else None
        rows.append(
            "<tr>"
            f'<td><span class="dot" style="background:{PHASE_COLOR[k]}"></span>'
            f"{esc(PHASE_LABEL[k])}</td>"
            f"<td class='num'>{fmt_dur(totals[k])}</td>"
            f"<td class='num'>{pct(totals[k], grand):.1f}%</td>"
            f"<td class='num'>{counts[k]}</td>"
            f"<td class='num'>{fmt_dur(avg)}</td>"
            f"<td class='num'>{fmt_dur(mx)}</td>"
            "</tr>"
        )
    rows.append(
        "<tr class='total-row'>"
        "<td><b>Total compute</b></td>"
        f"<td class='num'><b>{fmt_dur(grand)}</b></td>"
        "<td class='num'>100%</td>"
        f"<td class='num'>{len(run.components)}</td>"
        "<td class='num'>—</td><td class='num'>—</td></tr>"
    )

    return (
        '<section class="panel">'
        "<h2>Where did the time go?</h2>"
        '<p class="muted">Total time spent in each timed call, summed across all '
        "components. This is compute time (work done), not wall-clock — with "
        "concurrent workers the run finishes much faster than this sum.</p>"
        f"{legend()}"
        f'<div class="big-bar">{bar}</div>'
        '<table class="grid">'
        "<thead><tr><th>Call / phase</th><th class='num'>Total</th>"
        "<th class='num'>Share</th><th class='num'>Calls</th>"
        "<th class='num'>Avg</th><th class='num'>Max</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</section>"
    )


def grade_legend() -> str:
    items = [
        f'<span class="lg"><i style="background:{color}">{esc(glyph)}</i>'
        f'{esc(name)}</span>'
        for name, color, glyph in GRADES
    ]
    return f'<div class="legend">{"".join(items)}</div>'


def _mismatch_table(title: str, counter: Counter) -> str:
    if not counter:
        return ""
    total = sum(counter.values())
    rows = "".join(
        "<tr>"
        f"<td>{esc(reason)}</td>"
        f"<td class='num'>{n}</td>"
        f"<td class='num'>{pct(n, total):.0f}%</td>"
        "</tr>"
        for reason, n in counter.most_common()
    )
    return (
        f"<div class='mm-block'><h4>{esc(title)}</h4>"
        "<table class='grid mini'><thead><tr>"
        "<th>Bucket</th><th class='num'>Count</th><th class='num'>Share</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def accuracy_section(run: RunData) -> str:
    audit = run.audit
    if audit is None:
        return ""

    # Per-field grade breakdown: a stacked bar + counts table for each field.
    field_blocks = []
    for gf in audit.fields:
        c = audit.counts[gf]
        total = sum(c.values())
        segs = [(name, c[name], GRADE_COLOR[name]) for name in GRADE_ORDER]
        bar = stacked_bar(segs, total)
        rate = audit.hit_rate(gf)
        cells = "".join(
            f"<td class='num'>{c[name]}"
            f"<span class='sub'> {pct(c[name], total):.0f}%</span></td>"
            for name in GRADE_ORDER
        )
        field_blocks.append(
            "<tr>"
            f"<td class='name'>{esc(FIELD_LABEL[gf])}</td>"
            f"<td class='barcell'>{bar}</td>"
            f"{cells}"
            f"<td class='num total'><b>"
            f"{rate * 100:.1f}%</b></td>"
            "</tr>"
        )

    grade_headers = "".join(
        f"<th class='num'><span class='dot gdot' style='background:"
        f"{GRADE_COLOR[n]}'>{esc(GRADE_GLYPH[n])}</span>{esc(n)}</th>"
        for n in GRADE_ORDER
    )
    breakdown = (
        "<table class='grid'><thead><tr>"
        "<th>Field</th><th>Grade split</th>"
        f"{grade_headers}"
        "<th class='num'>Hit-rate</th>"
        f"</tr></thead><tbody>{''.join(field_blocks)}</tbody></table>"
    )

    # Mismatch root-cause: reason + ecosystem tables per field that had misses.
    mm_sections = []
    for gf in audit.fields:
        reasons = audit.mismatch_reasons[gf]
        ecos = audit.mismatch_ecosystems[gf]
        if not reasons and not ecos:
            continue
        mm_sections.append(
            f"<div class='mm-field'><h3>{esc(FIELD_LABEL[gf])} — "
            f"{sum(reasons.values())} mismatches</h3><div class='mm-grid'>"
            f"{_mismatch_table('By equality reason', reasons)}"
            f"{_mismatch_table('By ecosystem', ecos)}"
            "</div></div>"
        )
    mm_html = (
        "<h3 class='mm-head'>Why did mismatches happen?</h3>" + "".join(mm_sections)
        if mm_sections
        else "<p class='muted'>No mismatches recorded.</p>"
    )

    return (
        '<section class="panel">'
        "<h2>Accuracy</h2>"
        '<p class="muted">Grades are per field, from the audit run\'s ground '
        "truth. Hit-rate = Hit / (Hit + Mismatch + Unknown) — "
        "<b>Unscoreable</b> rows (ground truth itself unusable) are excluded "
        "from the denominator.</p>"
        f"{grade_legend()}"
        f"{breakdown}"
        f"<div class='mm'>{mm_html}</div>"
        "</section>"
    )


def overview_section(run: RunData) -> str:
    n = len(run.components)
    cache_hits = sum(1 for c in run.components if c.from_cache)
    timed = [c for c in run.components if c.total > 0]
    grand = sum(c.total for c in run.components)
    wall = run.wall_seconds

    cards = [stat_card("Components", str(n), f"{cache_hits} from cache")]
    if wall is not None:
        cards.append(stat_card("Wall time", fmt_dur(wall), "actual elapsed"))
    cards.append(
        stat_card(
            "Total compute", fmt_dur(grand), "summed across all timed calls"
        )
    )
    if wall and grand:
        cards.append(
            stat_card(
                "Effective parallelism",
                f"{grand / wall:.1f}×",
                f"workers configured: {run.info.get('workers', '?')}",
            )
        )
    if timed:
        totals = sorted(c.total for c in timed)
        median = statistics.median(totals)
        slowest = max(timed, key=lambda c: c.total)
        cards.append(
            stat_card(
                "Slowest component",
                fmt_dur(slowest.total),
                slowest.name,
            )
        )
        cards.append(stat_card("Median per component", fmt_dur(median)))
    if run.total_cost and run.total_cost != "unknown":
        cards.append(stat_card("Run cost", f"${run.total_cost}", "from summary.json"))
    if run.audit is not None:
        for gf in run.audit.fields:
            rate = run.audit.hit_rate(gf)
            c = run.audit.counts[gf]
            cards.append(
                stat_card(
                    f"{FIELD_LABEL[gf]} hit-rate",
                    f"{rate * 100:.1f}%" if rate is not None else "—",
                    f"{c['Hit']} hit / {c['Mismatch']} miss",
                )
            )

    info = run.info
    meta_rows = [
        ("Run", run.run_id),
        ("Model", info.get("model", "—")),
        ("Workers", info.get("workers", "—")),
        ("Started", fmt_iso(info.get("started_at_utc"))),
        ("Ended", fmt_iso(info.get("ended_at_utc"))),
    ]
    meta = "".join(
        f"<div><span class='k'>{esc(k)}</span><span class='v'>{esc(v)}</span></div>"
        for k, v in meta_rows
    )

    note = ""
    if run.summary is None:
        note = (
            '<p class="warn">No <code>summary.json</code> found — this run may '
            "still be in progress. Wall time and cost are unavailable; the "
            "figures below are built from the Story files that exist so far.</p>"
        )

    return (
        '<section class="panel">'
        f'<div class="run-meta">{meta}</div>'
        f"{note}"
        f'<div class="cards">{"".join(cards)}</div>'
        "</section>"
    )


def _sort_key(c: Component, k: str) -> float:
    return c.timings.get(k, 0.0)


def grade_chips(comp: Component) -> str:
    """Three small glyph badges (one per GT field), colored AND shaped by
    grade — checkmark/cross/etc., not color alone, so grade reads correctly
    for colorblind viewers even without the tooltip."""
    if not comp.grades:
        return ""
    chips = []
    for gf in GT_FIELDS:
        grade = comp.grades.get(gf)
        if grade is None:
            continue
        color = GRADE_COLOR.get(grade, "#767676")
        glyph = GRADE_GLYPH.get(grade, "?")
        chips.append(
            f'<i class="chip" style="background:{color}" '
            f'title="{esc(FIELD_LABEL[gf])}: {esc(grade)}">{esc(glyph)}</i>'
        )
    return f'<span class="chips">{"".join(chips)}</span>'


def component_table_section(run: RunData) -> str:
    comps = sorted(run.components, key=lambda c: c.total, reverse=True)
    max_total = max((c.total for c in comps), default=0.0)

    body_rows = []
    for i, c in enumerate(comps):
        segs = [
            (PHASE_LABEL[k], c.timings.get(k, 0.0), PHASE_COLOR[k])
            for k in PHASE_KEYS
        ]
        # Scale each component's bar against the slowest one for visual compare.
        bar = stacked_bar(segs, max_total if max_total > 0 else 1.0)
        cache_badge = (
            '<span class="badge cache">cache</span>' if c.from_cache else ""
        )
        phase_cells = "".join(
            f"<td class='num'>{fmt_dur(c.timings.get(k)) if k in c.timings else '·'}</td>"
            for k in PHASE_KEYS
        )
        detail = _component_detail(c)
        body_rows.append(
            f'<tr class="crow" data-total="{c.total:.6f}" '
            f'data-license="{_sort_key(c, "license"):.6f}" '
            f'data-download="{_sort_key(c, "download"):.6f}" '
            f'data-copyright="{_sort_key(c, "copyright"):.6f}" '
            f'onclick="tgl(this)">'
            f"<td class='rank'>{i + 1}</td>"
            f"<td class='name'>{esc(c.name)}{grade_chips(c)}{cache_badge}</td>"
            f"<td class='barcell'>{bar}</td>"
            f"{phase_cells}"
            f"<td class='num total'><b>{fmt_dur(c.total)}</b></td>"
            "</tr>"
            f'<tr class="drow"><td colspan="7">{detail}</td></tr>'
        )

    return (
        '<section class="panel">'
        "<h2>Per-component breakdown</h2>"
        '<p class="muted">Sorted slowest first. Bars are scaled to the slowest '
        "component. Click a row for the call details. Click a column header to "
        "re-sort.</p>"
        f"{legend()}"
        '<table class="grid comps" id="comps">'
        "<thead><tr>"
        "<th>#</th>"
        "<th data-sort='name'>Component</th>"
        "<th>Time split</th>"
        "<th class='num' data-sort='license'>License</th>"
        "<th class='num' data-sort='download'>Download</th>"
        "<th class='num' data-sort='copyright'>Copyright</th>"
        "<th class='num' data-sort='total'>Total</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
        "</section>"
    )


def _component_detail(c: Component) -> str:
    parts = [f"<div class='dk'>purl</div><div class='dv'>{esc(c.purl or '—')}</div>"]
    for gf in GT_FIELDS:
        grade = c.grades.get(gf)
        if grade is None:
            continue
        reason = c.eq_reasons.get(gf, "")
        reason_html = f" <span class='muted'>({esc(reason)})</span>" if reason else ""
        parts.append(
            f"<div class='dk'>{esc(FIELD_LABEL[gf])}</div>"
            f"<div class='dv'><span class='gtag' "
            f"style='background:{GRADE_COLOR.get(grade, '#cbd5e1')}'>{esc(grade)}"
            f"</span>{reason_html}</div>"
        )
    if c.from_cache:
        parts.append(
            "<div class='dk'>cache</div><div class='dv'>All fields served from "
            "cache — no calls made.</div>"
        )
    if c.license_attempts:
        parts.append(
            f"<div class='dk'>license attempts</div>"
            f"<div class='dv'>{esc(c.license_attempts)}</div>"
        )
    if c.download_outcome:
        parts.append(
            f"<div class='dk'>download</div>"
            f"<div class='dv'>{esc(c.download_outcome)}</div>"
        )
    if c.license_reason:
        parts.append(
            f"<div class='dk'>license reasoning</div>"
            f"<div class='dv'>{esc(c.license_reason)}</div>"
        )
    if c.copyright_reason:
        parts.append(
            f"<div class='dk'>copyright reasoning</div>"
            f"<div class='dv'>{esc(c.copyright_reason)}</div>"
        )
    return f"<div class='detail'>{''.join(parts)}</div>"


CSS = """
:root{
  --bg:#0f172a;--panel:#ffffff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;
  --soft:#f8fafc;
}
*{box-sizing:border-box}
body{margin:0;background:#eef2f7;color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:32px 20px 80px}
header.top{margin-bottom:24px}
header.top h1{margin:0 0 4px;font-size:24px;letter-spacing:-.02em}
header.top .sub{color:var(--muted);font-size:14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  padding:22px 24px;margin:0 0 20px;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.panel h2{margin:0 0 6px;font-size:18px;letter-spacing:-.01em}
.muted{color:var(--muted);font-size:13.5px;margin:0 0 16px;max-width:70ch}
.warn{background:#fef3c7;border:1px solid #fde68a;color:#92400e;padding:10px 14px;
  border-radius:10px;font-size:13.5px;margin:12px 0}
.run-meta{display:flex;flex-wrap:wrap;gap:8px 28px;margin-bottom:18px}
.run-meta .k{color:var(--muted);font-size:12px;text-transform:uppercase;
  letter-spacing:.04em;margin-right:8px}
.run-meta .v{font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}
.card{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card-label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.card-value{font-size:24px;font-weight:700;letter-spacing:-.02em;margin-top:4px}
.card-sub{color:var(--muted);font-size:12.5px;margin-top:2px}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:6px 0 14px;font-size:13px;color:var(--muted)}
.legend .lg{display:inline-flex;align-items:center;gap:6px}
.legend i{width:14px;height:14px;border-radius:3px;display:inline-flex;align-items:center;
  justify-content:center;font-style:normal;font-size:10px;font-weight:700;color:#fff;line-height:1}
.big-bar{margin:6px 0 20px}
.bar{display:flex;height:22px;width:100%;border-radius:6px;overflow:hidden;background:#eef2f7}
.bar.empty{background:repeating-linear-gradient(45deg,#f1f5f9,#f1f5f9 6px,#e2e8f0 6px,#e2e8f0 12px)}
.big-bar .bar{height:34px;border-radius:8px}
.seg{height:100%}
table.grid{width:100%;border-collapse:collapse;font-size:13.5px}
table.grid th,table.grid td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left}
table.grid th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.03em;
  font-weight:600}
table.grid td.num,table.grid th.num{text-align:right;font-variant-numeric:tabular-nums}
.total-row td{border-top:2px solid var(--line);border-bottom:none}
.dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px;vertical-align:middle}
.dot.gdot{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;
  font-size:9px;font-weight:700;color:#fff;font-style:normal}
table.comps th[data-sort]{cursor:pointer;user-select:none}
table.comps th[data-sort]:hover{color:var(--ink)}
table.comps td.rank{color:var(--muted);width:34px;text-align:right}
table.comps td.name{font-weight:600;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
table.comps td.barcell{width:34%}
table.comps td.total{white-space:nowrap}
.crow{cursor:pointer}
.crow:hover{background:var(--soft)}
.badge{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 7px;border-radius:999px;
  margin-left:8px;vertical-align:middle;text-transform:uppercase;letter-spacing:.03em}
.badge.cache{background:#e2e8f0;color:#475569}
.drow{display:none}
.drow.open{display:table-row}
.drow td{background:var(--soft)}
.detail{display:grid;grid-template-columns:150px 1fr;gap:6px 18px;padding:6px 2px;font-size:13px}
.detail .dk{color:var(--muted);text-align:right;text-transform:uppercase;font-size:11px;letter-spacing:.03em;padding-top:2px}
.detail .dv{white-space:pre-wrap;word-break:break-word}
.gtag{display:inline-block;color:#fff;font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;letter-spacing:.02em}
.chips{display:inline-flex;gap:3px;margin-left:8px;vertical-align:middle}
.chips .chip{width:13px;height:13px;border-radius:3px;display:inline-flex;align-items:center;
  justify-content:center;font-style:normal;font-size:9px;font-weight:700;color:#fff;line-height:1}
table.grid td .sub{color:var(--muted);font-size:11px;font-weight:400}
table.grid.mini{margin-top:4px}
table.grid.mini td,table.grid.mini th{padding:5px 8px;font-size:12.5px}
.mm{margin-top:22px}
.mm-head{font-size:15px;margin:0 0 8px}
.mm-field{margin:0 0 18px}
.mm-field h3{font-size:14px;margin:0 0 8px;color:var(--ink)}
.mm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:8px 26px}
.mm-block h4{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);margin:0 0 2px}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:24px}
code{background:#f1f5f9;padding:1px 5px;border-radius:5px;font-size:12.5px}
"""

JS = """
function tgl(row){
  var d = row.nextElementSibling;
  if(d && d.classList.contains('drow')) d.classList.toggle('open');
}
(function(){
  var tbl = document.getElementById('comps');
  if(!tbl) return;
  var dir = {};
  tbl.querySelectorAll('th[data-sort]').forEach(function(th){
    th.addEventListener('click', function(){
      var key = th.getAttribute('data-sort');
      dir[key] = !dir[key];
      var body = tbl.tBodies[0];
      // rows come in (main,detail) pairs; sort the pairs together
      var rows = Array.prototype.slice.call(body.querySelectorAll('tr.crow'));
      var pairs = rows.map(function(r){ return [r, r.nextElementSibling]; });
      pairs.sort(function(a,b){
        var av, bv;
        if(key==='name'){
          av = a[0].querySelector('td.name').innerText.toLowerCase();
          bv = b[0].querySelector('td.name').innerText.toLowerCase();
          return dir[key] ? (av<bv?-1:av>bv?1:0) : (av>bv?-1:av<bv?1:0);
        }
        av = parseFloat(a[0].getAttribute('data-'+key))||0;
        bv = parseFloat(b[0].getAttribute('data-'+key))||0;
        return dir[key] ? av-bv : bv-av;
      });
      var rank = 1;
      pairs.forEach(function(p){
        p[0].querySelector('td.rank').innerText = rank++;
        body.appendChild(p[0]); body.appendChild(p[1]);
      });
    });
  });
})();
"""


def build_html(run: RunData) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = f"Run-time report — {esc(run.run_id)}"
    body = (
        overview_section(run)
        + accuracy_section(run)
        + phase_breakdown_section(run)
        + component_table_section(run)
    )
    footer = (
        "<footer>Generated "
        f"{esc(generated)} from <code>{esc(run.run_dir)}</code>. "
        "Durations are from Story <code>timing_s=</code> lines. Equality-judge "
        "calls are not timed by the app and are excluded from compute totals."
        "</footer>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>{CSS}</style></head><body><div class='wrap'>"
        "<header class='top'>"
        f"<h1>{title}</h1>"
        f"<div class='sub'>SBOM Enricher run-time breakdown</div>"
        "</header>"
        f"{body}{footer}"
        f"</div><script>{JS}</script></body></html>"
    )


def write_runtime_report(run_dir: Path, out: Path | None = None) -> Path:
    """Load run artifacts, write HTML, return the path written."""
    run = load_run(run_dir)
    path = out or (run_dir / "runtime_report.html")
    path.write_text(build_html(run), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Path to a run directory")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output HTML path (default: <run_dir>/runtime_report.html)",
    )
    parser.add_argument(
        "--open", action="store_true", help="Open the report in a browser"
    )
    args = parser.parse_args(argv)

    run = load_run(args.run_dir)
    if not run.components:
        print(
            f"warning: no per-component stories found under {args.run_dir}",
            file=sys.stderr,
        )
    out = args.out or (args.run_dir / "runtime_report.html")
    out.write_text(build_html(run), encoding="utf-8")

    timed = sum(1 for c in run.components if c.total > 0)
    grand = sum(c.total for c in run.components)
    print(f"Wrote {out}")
    print(
        f"  components: {len(run.components)} ({timed} timed), "
        f"total compute: {fmt_dur(grand)}, "
        f"wall: {fmt_dur(run.wall_seconds)}"
    )
    if run.audit is not None:
        rates = ", ".join(
            f"{FIELD_LABEL[gf]} "
            f"{(run.audit.hit_rate(gf) or 0) * 100:.0f}%"
            for gf in run.audit.fields
        )
        print(f"  audit hit-rate: {rates}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
