"""Dependency-free inline SVG / HTML charts for the HTML reports.

Conventions (shared with the CSS in ``_style.css.j2``): single-series charts use one colour
(``--series-1``); bars are at most 18 px thick with a 4 px rounded data end and a square
baseline; value labels sit at the bar tip in text colour; hover tooltips come from a
``data-tip`` attribute (with a ``<title>`` fallback); every chart is accompanied by a table
view in the report.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

from markupsafe import Markup


@dataclass(frozen=True)
class Bar:
    label: str
    value: float
    display: str
    tip: str = ""
    muted: bool = False


def _bar_path(x0: float, y: float, width: float, height: float, radius: float = 4.0) -> str:
    """Horizontal bar with rounded data end (right) and square baseline (left)."""
    r = min(radius, width, height / 2)
    if width <= 0:
        return ""
    x1 = x0 + width
    return (f"M{x0:.1f},{y:.1f} H{x1 - r:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} "
            f"V{y + height - r:.1f} Q{x1:.1f},{y + height:.1f} {x1 - r:.1f},{y + height:.1f} "
            f"H{x0:.1f} Z")


def _col_path(x: float, y_base: float, width: float, height: float, radius: float = 4.0) -> str:
    """Vertical column with rounded top (data end) and square baseline."""
    if height <= 0:
        return ""
    r = min(radius, height, width / 2)
    y_top = y_base - height
    return (f"M{x:.1f},{y_base:.1f} V{y_top + r:.1f} Q{x:.1f},{y_top:.1f} {x + r:.1f},{y_top:.1f} "
            f"H{x + width - r:.1f} Q{x + width:.1f},{y_top:.1f} {x + width:.1f},{y_top + r:.1f} "
            f"V{y_base:.1f} Z")


# Presentation attributes make the SVG self-contained (PDF renderers, image viewers, e-mail
# clients ignore the page's CSS). In browsers the CSS rules in _style.css.j2 / app.css take
# precedence over presentation attributes, so the light/dark themes still apply.
_BAR_FILL = "#2a78d6"
_MUTED_FILL = "#c3c2b7"
_LABEL = 'fill="#52514e" font-size="12"'
_VALUE = 'fill="#0b0b0b" font-size="12"'
_BASELINE = 'stroke="#c3c2b7" stroke-width="1"'


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def hbar_chart(bars: Sequence[Bar], *, title: str, label_width: int = 190,
               width: int = 500, bar_height: int = 16, gap: int = 10) -> Markup:
    """Ranked horizontal bar chart (largest first). Returns an accessible inline SVG."""
    if not bars:
        return Markup('<p class="muted small">No data.</p>')
    max_value = max(b.value for b in bars) or 1.0
    value_space = 56
    plot = width - label_width - value_space
    row = bar_height + gap
    height = row * len(bars) + 8
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)}" preserveAspectRatio="xMinYMin meet">',
        f"<title>{escape(title)}</title>",
        f'<line class="baseline" x1="{label_width}" x2="{label_width}" y1="0" y2="{height - 4}" '
        f'{_BASELINE}/>',
    ]
    for i, b in enumerate(bars):
        y = 4 + i * row
        w = max(plot * (b.value / max_value), 0.0)
        tip = escape(b.tip or f"{b.label}: {b.display}")
        css = "bar muted" if b.muted else "bar"
        parts.append(f'<g data-tip="{tip}"><title>{tip}</title>')
        parts.append(f'<rect x="0" y="{y - gap / 2:.1f}" width="{width}" height="{row}" '
                     'fill="transparent"/>')
        label = escape(_truncate(b.label, max(12, label_width // 7)))
        parts.append(f'<text x="{label_width - 10}" y="{y + bar_height / 2 + 4:.1f}" {_LABEL} '
                     f'text-anchor="end">{label}</text>')
        if w > 0:
            path = _bar_path(label_width + 1, y, w, bar_height)
            fill = _MUTED_FILL if b.muted else _BAR_FILL
            parts.append(f'<path class="{css}" fill="{fill}" d="{path}"/>')
        parts.append(f'<text class="value-label" {_VALUE} x="{label_width + 1 + w + 8:.1f}" '
                     f'y="{y + bar_height / 2 + 4:.1f}">{escape(b.display)}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    # bandit B704: every interpolated value is escaped (tests: test_xss_*)
    return Markup("".join(parts))  # nosec B704


def column_chart(bars: Sequence[Bar], *, title: str, width: int = 500, height: int = 200,
                 col_width: int = 24) -> Markup:
    """Column chart for a small number of ordered categories (e.g. chain depth)."""
    if not bars:
        return Markup('<p class="muted small">No data.</p>')
    max_value = max(b.value for b in bars) or 1.0
    top_pad, bottom_pad = 24, 40
    plot_h = height - top_pad - bottom_pad
    slot = width / len(bars)
    base = height - bottom_pad
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)}">',
        f"<title>{escape(title)}</title>",
        f'<line class="baseline" x1="0" x2="{width}" y1="{base}" y2="{base}" {_BASELINE}/>',
    ]
    for i, b in enumerate(bars):
        cx = slot * i + slot / 2
        h = plot_h * (b.value / max_value)
        tip = escape(b.tip or f"{b.label}: {b.display}")
        parts.append(f'<g data-tip="{tip}"><title>{tip}</title>')
        parts.append(f'<rect x="{slot * i:.1f}" y="0" width="{slot:.1f}" height="{height}" '
                     'fill="transparent"/>')
        if h > 0:
            path = _col_path(cx - col_width / 2, base, col_width, h)
            parts.append(f'<path class="bar" fill="{_BAR_FILL}" d="{path}"/>')
        parts.append(f'<text class="value-label" {_VALUE} x="{cx:.1f}" y="{base - h - 8:.1f}" '
                     f'text-anchor="middle">{escape(b.display)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{base + 18}" {_LABEL} text-anchor="middle">'
                     f'{escape(_truncate(b.label, 22))}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    # bandit B704: every interpolated value is escaped (tests: test_xss_*)
    return Markup("".join(parts))  # nosec B704


@dataclass(frozen=True)
class Segment:
    label: str
    value: float
    display: str
    color_var: str


def segmented_bar(segments: Sequence[Segment], *, title: str) -> Markup:
    """Part-to-whole bar (≤ 6 segments) with a legend carrying the values."""
    segs = [s for s in segments if s.value > 0]
    total = sum(s.value for s in segs)
    if not segs or total <= 0:
        return Markup('<p class="muted small">No data.</p>')
    bar = "".join(
        f'<span style="flex:{s.value / total:.6f};background:var({escape(s.color_var)})" '
        f'data-tip="{escape(s.label)}: {escape(s.display)}" '
        f'title="{escape(s.label)}: {escape(s.display)}"></span>'
        for s in segs
    )
    legend = "".join(
        f'<span><i class="key" style="background:var({escape(s.color_var)})"></i>'
        f"{escape(s.label)} · <strong>{escape(s.display)}</strong></span>"
        for s in segs
    )
    # bandit B704: every interpolated value is escaped (test_xss_*)
    return Markup(  # nosec B704
        f'<div role="img" aria-label="{escape(title)}"><div class="seg-bar">{bar}</div>'
        f'<div class="legend">{legend}</div></div>')


TOOLTIP_SCRIPT = Markup("""<div id="viz-tip" role="tooltip" style="position:fixed;
pointer-events:none;display:none;z-index:10;background:var(--surface-1);
color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:6px 10px;
font-size:13px;box-shadow:0 4px 16px rgba(0,0,0,.12);max-width:320px"></div>
<script>
(function () {
  var t = document.getElementById("viz-tip");
  document.addEventListener("mousemove", function (e) {
    var n = e.target.closest && e.target.closest("[data-tip]");
    if (!n) { t.style.display = "none"; return; }
    t.textContent = n.getAttribute("data-tip");
    t.style.display = "block";
    var x = e.clientX + 14, y = e.clientY + 14;
    if (x + t.offsetWidth > innerWidth - 8) { x = e.clientX - t.offsetWidth - 14; }
    if (y + t.offsetHeight > innerHeight - 8) { y = e.clientY - t.offsetHeight - 14; }
    t.style.left = x + "px";
    t.style.top = y + "px";
  });
  document.querySelectorAll("[data-tip] title").forEach(function (n) { n.remove(); });
  document.querySelectorAll("[data-tip][title]").forEach(function (n) {
    n.removeAttribute("title");
  });
})();
</script>""")
