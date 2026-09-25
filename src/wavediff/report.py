"""Self-contained HTML report generation.

The report is the artefact people actually look at, so it is rendered as one
portable file: inline CSS, inline SVG, no scripts and no network fetches. It
can be attached to a CI run, dropped in a PR comment, or opened from a shared
drive without any server.

Every divergent signal gets a two-lane panel (A on top, B below) covering the
window around the first disagreement, with the disagreeing intervals shaded.
"""

from __future__ import annotations

from html import escape

from .diff import ONLY_A, ONLY_B, DiffResult, DiffRun, SignalDiff
from .model import Trace, format_value

__all__ = ["render_html", "render_summary_text"]

_PANEL_WIDTH = 900
_LABEL_WIDTH = 210
_LANE_HEIGHT = 34
_LANE_GAP = 6
_PLOT_PAD = 10
_MAX_PANELS = 40


def _level(value: str) -> float | None:
    """Map a scalar value to a drawable level; ``None`` means unknown."""
    if value == "1":
        return 1.0
    if value == "0":
        return 0.0
    return None


def _segments_in_window(trace: Trace, t0: int, t1: int) -> list[tuple[int, int, str]]:
    """Slice a trace into ``(start, end, value)`` segments clipped to a window."""
    if t1 <= t0:
        t1 = t0 + 1
    value = trace.value_at(t0)
    cursor = t0
    segments: list[tuple[int, int, str]] = []
    for time, new_value in zip(trace.times, trace.values):
        if time <= t0:
            value = new_value
            continue
        if time >= t1:
            break
        segments.append((cursor, time, value))
        cursor = time
        value = new_value
    segments.append((cursor, t1, value))
    return [seg for seg in segments if seg[1] > seg[0]]


def _time_axis(t0: int, t1: int, x_of) -> str:
    parts = []
    span = max(t1 - t0, 1)
    step = span / 8
    for k in range(9):
        t = t0 + step * k
        x = x_of(int(t))
        parts.append(
            f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="10" stroke="#cbd5e1" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="24" text-anchor="middle" font-size="10" fill="#64748b">{int(t)}</text>'
        )
    return "".join(parts)


def _scalar_lane(trace: Trace, t0: int, t1: int, x_of, y_top: float, color: str) -> str:
    """Orthogonal step waveform for a 1-bit signal.

    Segments are joined by explicit vertical edges. Without them the trace
    renders as a row of disconnected dashes, which is unreadable to anyone who
    has looked at a real waveform viewer.
    """
    segments = _segments_in_window(trace, t0, t1)
    lo, hi = y_top + _LANE_HEIGHT - 6, y_top + 6
    mid = y_top + _LANE_HEIGHT / 2

    def level_y(value: str) -> float:
        lvl = _level(value)
        return mid if lvl is None else lo - lvl * (lo - hi)

    steps: list[str] = []
    dashed: list[str] = []
    for index, (start, end, value) in enumerate(segments):
        x1, x2 = x_of(start), x_of(end)
        y = level_y(value)
        # Each segment opens with a vertical edge at x1 (a no-op when the level
        # did not change), then runs horizontally to x2.
        steps.append(f"{'M' if index == 0 else 'L'} {x1:.1f} {y:.1f}")
        steps.append(f"L {x2:.1f} {y:.1f}")
        if _level(value) is None:
            dashed.append(f"M {x1:.1f} {y:.1f} L {x2:.1f} {y:.1f}")

    out = [f'<path d="{" ".join(steps)}" fill="none" stroke="{color}" stroke-width="2.2"/>']
    if dashed:
        out.append(
            f'<path d="{" ".join(dashed)}" fill="none" stroke="{color}" stroke-width="2.2" '
            f'stroke-dasharray="4 3" opacity="0.6"/>'
        )
    return "".join(out)


def _bus_lane(trace: Trace, t0: int, t1: int, x_of, y_top: float, color: str,
              width: int, radix: str) -> str:
    """Value-band rendering for multi-bit signals, labelled at each change."""
    segments = _segments_in_window(trace, t0, t1)
    # Wide buses are unreadable in binary, so they widen to hex on their own.
    lane_radix = "hex" if (width > 16 and radix == "bin") else radix
    out = []
    for idx, (start, end, value) in enumerate(segments):
        x1, x2 = x_of(start), x_of(end)
        width_px = x2 - x1
        fill = "#ffffff" if idx % 2 == 0 else "#f1f5f9"
        out.append(
            f'<rect x="{x1:.1f}" y="{y_top:.1f}" width="{width_px:.1f}" height="{_LANE_HEIGHT}" '
            f'fill="{fill}" stroke="{color}" stroke-width="1.2"/>'
        )
        if width_px > 34:
            label = format_value(value, width, lane_radix)
            if len(label) > 10:
                label = label[:9] + "…"
            out.append(
                f'<text x="{x1 + width_px / 2:.1f}" y="{y_top + _LANE_HEIGHT / 2 + 4:.1f}" '
                f'text-anchor="middle" font-size="11" font-family="ui-monospace, monospace" '
                f'fill="#334155">{escape(label)}</text>'
            )
    return "".join(out)


def _panel(sig: SignalDiff, a_traces, b_traces, offset: int, t_end: int, radix: str) -> str:
    first = sig.first_divergence or 0
    last = max((r.end for r in sig.runs if r.end is not None), default=first)
    span = max(t_end, first, 1)
    padding = max((last - first) // 4, max(span // 40, 10))
    t0 = max(0, first - padding)
    t1 = min(max(last + padding, first + padding), max(span, first + padding))
    if t1 <= t0:
        t1 = t0 + 1

    plot_w = _PANEL_WIDTH - _LABEL_WIDTH - _PLOT_PAD * 2

    def x_of(t: int) -> float:
        return _LABEL_WIDTH + _PLOT_PAD + (t - t0) / (t1 - t0) * plot_w

    lane_a_top = 6.0
    lane_b_top = lane_a_top + _LANE_HEIGHT + _LANE_GAP
    height = lane_b_top + _LANE_HEIGHT + 30

    trace_a = a_traces.get(sig.name)
    trace_b = b_traces.get(sig.name)

    body = []
    body.append(f'<rect x="0" y="0" width="{_PANEL_WIDTH}" height="{height}" fill="#ffffff"/>')

    # Shade the disagreeing intervals behind both lanes.
    for run in sig.runs:
        rx1 = x_of(max(run.start, t0))
        rx2 = x_of(run.end if run.end is not None else t1)
        body.append(
            f'<rect x="{rx1:.1f}" y="{lane_a_top - 3:.1f}" width="{max(rx2 - rx1, 1.5):.1f}" '
            f'height="{lane_b_top + _LANE_HEIGHT - lane_a_top + 6:.1f}" fill="#dc2626" opacity="0.10"/>'
        )

    if sig.status in (ONLY_A, ONLY_B):
        body.append(
            f'<text x="{_LABEL_WIDTH + 20}" y="{lane_a_top + _LANE_HEIGHT}" font-size="13" fill="#b91c1c">'
            f'present only in {"A" if sig.status == ONLY_A else "B"}</text>'
        )
    else:
        for label, trace, top, color in (
            ("A", trace_a, lane_a_top, "#2563eb"),
            ("B", trace_b, lane_b_top, "#7c3aed"),
        ):
            body.append(
                f'<text x="12" y="{top + _LANE_HEIGHT / 2 + 4:.1f}" font-size="11" fill="#64748b" '
                f'font-family="ui-monospace, monospace">{label}</text>'
            )
            if trace is None:
                continue
            shifted = trace
            if offset and label == "B":
                shifted = Trace(
                    signal=trace.signal,
                    times=[t + offset for t in trace.times],
                    values=list(trace.values),
                    initial=trace.initial,
                )
            if sig.width <= 1:
                body.append(_scalar_lane(shifted, t0, t1, x_of, top, color))
            else:
                body.append(_bus_lane(shifted, t0, t1, x_of, top, color, sig.width, radix))

    body.append(f'<g transform="translate({_LABEL_WIDTH + _PLOT_PAD}, {height - 28})">{_time_axis(t0, t1, lambda t: x_of(t) - _LABEL_WIDTH - _PLOT_PAD)}</g>')

    width_note = f"{sig.width} bit" + ("s" if sig.width > 1 else "")
    header = (
        f'<div class="sig-head"><code>{escape(sig.name)}</code>'
        f'<span class="meta">{width_note} &middot; {len(sig.runs)} differing interval(s)'
        f' &middot; first at t={first}</span></div>'
    )
    return (
        f'<section class="panel">{header}'
        f'<svg viewBox="0 0 {_PANEL_WIDTH} {height}" width="100%" role="img" '
        f'aria-label="waveform comparison for {escape(sig.name)}">{"".join(body)}</svg></section>'
    )


def _run_table(runs: list[DiffRun], radix: str) -> str:
    rows = []
    for run in runs[:200]:
        rows.append(
            "<tr>"
            f"<td class='mono'>{run.describe_time()}</td>"
            f"<td class='mono'>{escape(format_value(run.value_a, run.width, radix))}</td>"
            f"<td class='mono'>{escape(format_value(run.value_b, run.width, radix))}</td>"
            f"<td>{'open' if run.duration is None else run.duration}</td>"
            "</tr>"
        )
    extra = ""
    if len(runs) > 200:
        extra = f'<p class="note">{len(runs) - 200} further intervals omitted.</p>'
    return (
        "<table class='runs'><thead><tr><th>interval (A timeline)</th><th>A</th><th>B</th>"
        f"<th>duration</th></tr></thead><tbody>{''.join(rows)}</tbody></table>{extra}"
    )


def render_html(
    result: DiffResult,
    *,
    a_path: str,
    b_path: str,
    title: str = "wavediff report",
    radix: str = "bin",
) -> str:
    """Render a complete, standalone HTML report for ``result``."""
    counts = result.counts()
    first = result.first_divergence
    ts = result.timescale

    if result.identical:
        verdict = '<div class="verdict ok">IDENTICAL &mdash; no signal diverged</div>'
    else:
        verdict = (
            f'<div class="verdict bad">DIVERGED &mdash; first difference at t={first} '
            f'({escape(ts)}) in {counts["differ"]} signal(s)</div>'
        )

    rows = []
    for sig in sorted(result.signals, key=lambda s: (not s.differs, s.first_divergence or 0, s.name)):
        if sig.status == "match":
            badge = '<span class="badge ok">match</span>'
        elif sig.status == "differ":
            badge = '<span class="badge bad">differ</span>'
        elif sig.status == ONLY_A:
            badge = '<span class="badge warn">only in A</span>'
        else:
            badge = '<span class="badge warn">only in B</span>'
        rows.append(
            "<tr>"
            f"<td class='mono'>{escape(sig.name)}</td>"
            f"<td>{sig.width}</td>"
            f"<td>{badge}</td>"
            f"<td class='mono'>{'' if sig.first_divergence is None else sig.first_divergence}</td>"
            f"<td>{len(sig.runs)}</td>"
            "</tr>"
        )

    panels = []
    for sig in result.differing[:_MAX_PANELS]:
        panel = _panel(
            sig, result.a_traces, result.b_traces, result.alignment.offset, result.a_end, radix
        )
        runs_html = _run_table(sig.runs, radix) if sig.runs else ""
        panels.append(f'{panel}{runs_html}')
    if len(result.differing) > _MAX_PANELS:
        panels.append(
            f'<p class="note">{len(result.differing) - _MAX_PANELS} further divergent signals '
            f'omitted from the graphical section; see the table above.</p>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 32px 24px 64px; background: #f1f5f9; color: #0f172a;
         font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  .wrap {{ max-width: 1000px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; font-weight: 650; }}
  .sub {{ color: #64748b; font-size: 13px; margin-bottom: 20px; }}
  .verdict {{ padding: 14px 18px; border-radius: 10px; font-weight: 600; font-size: 15px;
              margin-bottom: 20px; border: 1px solid; }}
  .verdict.ok {{ background: #f0fdf4; border-color: #86efac; color: #15803d; }}
  .verdict.bad {{ background: #fef2f2; border-color: #fca5a5; color: #b91c1c; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
           padding: 16px 18px; margin-bottom: 18px; }}
  .card h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
              color: #64748b; margin: 0 0 12px; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; color: #64748b; font-weight: 600; font-size: 11px;
        text-transform: uppercase; letter-spacing: .05em; padding: 6px 8px;
        border-bottom: 1px solid #e2e8f0; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #f1f5f9; }}
  .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
  .badge {{ display: inline-block; padding: 1px 8px; border-radius: 999px;
            font-size: 11px; font-weight: 600; }}
  .badge.ok {{ background: #dcfce7; color: #15803d; }}
  .badge.bad {{ background: #fee2e2; color: #b91c1c; }}
  .badge.warn {{ background: #fef3c7; color: #b45309; }}
  .panel {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
            padding: 12px 14px; margin-bottom: 14px; }}
  .sig-head {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline;
               margin-bottom: 6px; }}
  .sig-head code {{ font-size: 13px; font-weight: 600; color: #0f172a; }}
  .meta {{ font-size: 11px; color: #64748b; }}
  .runs {{ margin-top: 8px; font-size: 12px; }}
  .note {{ font-size: 12px; color: #64748b; }}
  footer {{ margin-top: 26px; font-size: 12px; color: #94a3b8; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{escape(title)}</h1>
  <div class="sub">
    <code>A</code> = {escape(a_path)} &nbsp;&middot;&nbsp;
    <code>B</code> = {escape(b_path)}<br/>
    timescale {escape(ts)} &nbsp;&middot;&nbsp; alignment: {escape(result.alignment.describe())}
  </div>
  {verdict}
  <div class="card">
    <h2>Signals</h2>
    <table>
      <thead><tr><th>signal</th><th>width</th><th>status</th><th>first diff</th><th>intervals</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
  {'<div class="card"><h2>Divergent signals</h2></div>' if panels else ''}
  {''.join(panels)}
  <footer>generated by wavediff</footer>
</div>
</body>
</html>
"""


def render_summary_text(
    result: DiffResult, *, a_path: str, b_path: str, radix: str = "bin"
) -> str:
    """Plain-text summary for terminals and CI logs."""
    counts = result.counts()
    lines = [
        f"A: {a_path}",
        f"B: {b_path}",
        f"alignment: {result.alignment.describe()}",
        "",
    ]
    if result.identical:
        lines.append(f"IDENTICAL  ({counts['match']} signals compared, no differences)")
        return "\n".join(lines)

    first = result.first_divergence
    lines.append(
        f"DIVERGED  first difference at t={first} ({result.timescale}); "
        f"{counts['differ']} differ, {counts['match']} match, "
        f"{counts[ONLY_A]} only in A, {counts[ONLY_B]} only in B"
    )
    lines.append("")
    for sig in sorted(result.differing, key=lambda s: (s.first_divergence or 0, s.name)):
        if sig.status == ONLY_A:
            lines.append(f"  [only in A]  {sig.name}")
            continue
        if sig.status == ONLY_B:
            lines.append(f"  [only in B]  {sig.name}")
            continue
        head = sig.runs[0]
        lines.append(
            f"  t={head.start:<10} {sig.name:<40} "
            f"A={format_value(head.value_a, sig.width, radix):<12} "
            f"B={format_value(head.value_b, sig.width, radix):<12} "
            f"({len(sig.runs)} interval(s))"
        )
    return "\n".join(lines)
