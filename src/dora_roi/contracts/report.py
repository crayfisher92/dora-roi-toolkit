"""Remediation plan for a client: print-friendly HTML and an Excel workbook (EN/DE)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dora_roi import __version__
from dora_roi.contracts.analysis import RemediationPlan, gaps_by_provision
from dora_roi.contracts.provisions import PROVISIONS, clause_label
from dora_roi.i18n import format_date, translator
from dora_roi.io.sheets import SheetBook
from dora_roi.reporting.env import environment


def render_plan_html(plan: RemediationPlan, *, lang: str = "en", client: str | None = None,
                     prepared_by: str | None = None) -> str:
    """Render the remediation plan as a self-contained HTML page."""
    t = translator(lang)
    context: dict[str, Any] = {
        "plan": plan, "pf": plan.portfolio, "t": t, "lang": lang,
        "client": client or "", "prepared_by": prepared_by,
        "generated": datetime.now(UTC), "version": __version__,
        "fmt": lambda d: format_date(d, lang), "clause_label": clause_label,
        "by_provision": gaps_by_provision(plan.portfolio),
        "providers": [p for p in plan.portfolio.providers if p.with_gaps or p.critical][:40],
    }
    return environment().get_template("remediation.html.j2").render(**context)


_PRIO_FILL = {"high": "#F8D7D7", "medium": "#FDEBC8", "low": "#E3F1E3"}


def write_plan_workbook(plan: RemediationPlan, path: Path, *, lang: str = "en",
                        client: str | None = None) -> Path:
    """Write the remediation plan as an Excel workbook the client can work in."""
    t = translator(lang)
    de = lang == "de"
    with SheetBook(path) as wb:
        rows: list[list[Any]] = []
        formats: dict[tuple[int, int], Any] = {}
        for n, i in enumerate(plan.items, start=1):
            note = []
            if i.inherited_from:
                note.append(t("c30.inherited", ref=i.inherited_from))
            if i.applies_to:
                note.append(t("c30.applies_to", refs=", ".join(i.applies_to)))
            rows.append([n, t(f"prio.{i.priority.value}"), i.providers, i.contract_ref,
                         i.entities, i.critical_functions or "—", i.provision.title(lang),
                         i.provision.article, t(f"st.{i.status.value}"), i.clause_ref,
                         i.evidence, i.action(lang), i.target_date, i.contract_end, "", "",
                         "; ".join(note)])
            formats[(n, 1)] = wb.fill(_PRIO_FILL[i.priority.value])
        wb.sheet("Maßnahmenplan" if de else "Remediation plan",
                 ["#", t("g.priority"), t("g.provider"), t("g.contract"), t("g.entity"),
                  t("c30.critical_functions"), t("c30.provision"), "Art.", t("g.status"),
                  t("c30.clause"), t("c30.evidence"), t("g.action"), t("g.target"),
                  t("g.contract_end"), t("g.owner"), t("g.status") + " (client)", t("g.notes")],
                 rows, (5, 10, 30, 16, 28, 34, 40, 18, 11, 12, 48, 56, 12, 12, 18, 16, 30),
                 lists={15: ("open", "in negotiation", "agreed", "signed", "accepted risk")},
                 cell_formats=formats, extra_rows=200)
        wb.sheet("Nach Dienstleister" if de else "By provider",
                 [t("g.provider"), t("c30.critical_functions"), t("g.contracts"),
                  t("c30.assessed"), t("c30.with_gaps"), t("st.missing"), t("st.partial"),
                  t("g.status")],
                 [[p.name, len(p.critical_functions), len(p.contracts), p.assessed,
                   p.with_gaps, p.missing, p.partial, t(f"cs.{p.status.value}")]
                  for p in plan.portfolio.providers],
                 (36, 14, 12, 12, 12, 10, 10, 22))
        wb.sheet("Ausnahmen" if de else "Exceptions",
                 [t("g.provider"), t("g.contract"), t("c30.provision"), "Art.", t("g.status"),
                  t("c30.ui.ex.reason"), t("c30.ui.ex.approver"), t("c30.ui.ex.until")],
                 [[e.providers, e.contract_ref, e.provision.title(lang), e.provision.article,
                   t(f"st.{e.status.value}"), e.reason, e.approver, e.until]
                  for e in plan.exceptions],
                 (30, 16, 40, 18, 11, 60, 24, 14))
        wb.sheet("Zu bewerten" if de else "To assess",
                 [t("g.contract"), t("g.provider"), t("g.critical"), t("g.status"),
                  t("c30.critical_functions")],
                 [[c.ref, c.context.provider_names,
                   t("g.yes") if c.context.critical else t("g.no"), t(f"cs.{c.status.value}"),
                   "; ".join(f"{f.function_id} {f.name}" for f in c.context.critical_functions)]
                  for c in plan.to_assess],
                 (16, 36, 14, 24, 60))
        wb.sheet("Checkliste" if de else "Checklist",
                 ["ID", "Art.", t("c30.provision"), "Scope", "Requirement", t("g.action")],
                 [[pr.id, pr.article, pr.title(lang), pr.scope.value, pr.requirement(lang),
                   pr.remediation(lang)] for pr in PROVISIONS],
                 (11, 20, 44, 10, 80, 70))
        wb.text_sheet("README", (
            t("c30.plan.title") + (f" – {client}" if client else ""),
            t("g.prepared", date=format_date(plan.plan_date, lang)),
            t("c30.method"), t("g.disclaimer"), f"dora-roi-toolkit {__version__}"), 120)
    return path
