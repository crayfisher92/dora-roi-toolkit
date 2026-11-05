"""Executive summary (HTML) of ICT third-party concentration risk, for a CRO audience."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from markupsafe import Markup

from dora_roi import __version__
from dora_roi.analytics import AnalyticsConfig, ConcentrationAnalysis, analyse
from dora_roi.model import RegisterOfInformation
from dora_roi.reporting.charts import (
    TOOLTIP_SCRIPT,
    Bar,
    Segment,
    column_chart,
    hbar_chart,
    segmented_bar,
)
from dora_roi.reporting.env import environment
from dora_roi.validation import ValidationReport

REGION_COLORS = {
    "EU": "--series-1",
    "Switzerland": "--series-2",
    "EEA (non-EU)": "--series-3",
    "Third country": "--series-4",
    "Unknown": "--series-muted",
}
REGION_ORDER = list(REGION_COLORS)
SUBST_COLORS = {
    "EASY": "--ord-1",
    "MEDIUM": "--ord-2",
    "HIGHLY_COMPLEX": "--ord-3",
    "NOT_SUBSTITUTABLE": "--ord-4",
    "NOT_ASSESSED": "--series-muted",
}


#: rows of the provider-group table in the PDF (each page of a long table costs ~0.1 s)
PDF_GROUP_LIMIT = 50

def money(value: Decimal | float | int, currency: str | None = None) -> str:
    """Compact money format: ``EUR 12.4m``, ``CHF 850k``."""
    v = float(value)
    prefix = f"{currency} " if currency else ""
    if abs(v) >= 1e9:
        return f"{prefix}{v / 1e9:.1f}bn"
    if abs(v) >= 1e6:
        return f"{prefix}{v / 1e6:.1f}m"
    if abs(v) >= 1e3:
        return f"{prefix}{v / 1e3:.0f}k"
    return f"{prefix}{v:,.0f}"


def pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def build_charts(a: ConcentrationAnalysis, top_n: int = 10) -> dict[str, Markup]:
    cur = a.reporting_currency
    groups = a.groups[:top_n]
    charts: dict[str, Markup] = {
        "groups": hbar_chart(
            [Bar(g.group_name, g.spend_share, pct(g.spend_share),
                 f"{g.group_name}: {pct(g.spend_share)} of spend · {money(g.spend, cur)} · "
                 f"{g.contracts} arrangement(s) · {g.critical_functions_incl_indirect} critical "
                 f"function(s), {g.critical_functions} directly")
             for g in groups],
            title="Share of annual ICT third-party spend by provider group"),
    }
    # direct + indirect (through subcontracting), including pure fourth parties (B-25)
    cif_rows: dict[str, tuple[int, int]] = {
        g.group_name: (g.critical_functions_incl_indirect, g.critical_functions)
        for g in a.groups if g.critical_functions_incl_indirect}
    for s in a.subcontractors:
        if s.group_name not in cif_rows and s.critical_functions:
            cif_rows[s.group_name] = (s.critical_functions, 0)
    cif = sorted(cif_rows.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))[:top_n]
    charts["cif"] = hbar_chart(
        [Bar(name, total, str(total),
             f"{name}: {total} critical function(s) depend on it, {direct} through a direct "
             "contract")
         for name, (total, direct) in cif],
        title="Critical or important functions depending on each provider group, including "
        "through subcontracting")
    regions = sorted(a.hq_regions, key=lambda r: REGION_ORDER.index(r.key)
                     if r.key in REGION_ORDER else 99)
    charts["regions"] = segmented_bar(
        [Segment(r.label, r.share, f"{pct(r.share)} · {r.count} provider(s)",
                 REGION_COLORS.get(r.key, "--series-muted")) for r in regions],
        title="Spend by provider headquarters region")
    gregions = sorted(a.group_regions, key=lambda r: REGION_ORDER.index(r.key)
                      if r.key in REGION_ORDER else 99)
    charts["group_regions"] = segmented_bar(
        [Segment(r.label, r.share, f"{pct(r.share)} · {r.count} group(s)",
                 REGION_COLORS.get(r.key, "--series-muted")) for r in gregions],
        title="Spend by headquarters region of the ultimate parent")
    charts["countries"] = hbar_chart(
        [Bar(c.label, c.share, pct(c.share), f"{c.label}: {pct(c.share)} of spend · "
             f"{c.count} provider(s)") for c in a.hq_countries[:top_n]],
        title="Share of spend by provider headquarters country")
    charts["depth"] = column_chart(
        [Bar(d.label, d.count, str(d.count), f"{d.label}: {d.count} arrangement(s)")
         for d in a.chain_depths],
        title="Arrangements by deepest reported subcontracting rank")
    charts["subcontractors"] = hbar_chart(
        [Bar(s.name, s.chains, str(s.chains),
             f"{s.name}: in {s.chains} chain(s), {s.critical_chains} supporting critical "
             "functions")
         for s in a.subcontractors[:top_n]],
        title="Subcontractors appearing in the most supply chains")
    charts["substitutability"] = segmented_bar(
        [Segment(s.label, s.share, f"{pct(s.share)} · {s.count}",
                 SUBST_COLORS.get(s.key, "--series-muted")) for s in a.substitutability_critical],
        title="Substitutability of ICT services supporting critical functions")
    charts["service_types"] = hbar_chart(
        [Bar(s.label, s.count, str(s.count), f"{s.label}: {s.count} service row(s) · "
             f"{money(s.spend, cur)}") for s in a.service_types[:top_n]],
        title="ICT services by type", label_width=300, width=1040)
    return charts


def render_executive_summary(
    register: RegisterOfInformation,
    validation: ValidationReport | None = None,
    *,
    analysis: ConcentrationAnalysis | None = None,
    config: AnalyticsConfig | None = None,
    client_name: str | None = None,
    prepared_by: str | None = None,
    pdf: bool = False,
) -> str:
    """Render the executive summary HTML page (``pdf=True``: print variant for PDF)."""
    cfg = config or AnalyticsConfig()
    a = analysis or analyse(register, cfg)
    context: dict[str, Any] = {
        "a": a,
        "cfg": cfg,
        "charts": build_charts(a, cfg.top_n),
        "validation": validation,
        "client": client_name or a.entity_name or "Register of information",
        "prepared_by": prepared_by,
        "generated": datetime.now(UTC),
        "version": __version__,
        "money": money,
        "pct": pct,
        "tooltip_script": TOOLTIP_SCRIPT,
        "single_cif": [f for f in a.critical_functions if f.single_provider],
        "pdf": pdf,
        "pdf_group_limit": PDF_GROUP_LIMIT,
    }
    return environment().get_template("executive.html.j2").render(**context)


def render_executive_pdf(
    register: RegisterOfInformation,
    validation: ValidationReport | None = None,
    **kwargs: Any,
) -> bytes:
    """PDF executive summary (needs the optional WeasyPrint dependency)."""
    from dora_roi.reporting.pdf import html_to_pdf

    return html_to_pdf(render_executive_summary(register, validation, pdf=True, **kwargs))
