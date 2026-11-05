"""Remediation plan for a client: print-friendly HTML and an Excel workbook (EN/DE)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from dora_roi import __version__
from dora_roi.contracts.analysis import RemediationPlan, gaps_by_provision
from dora_roi.contracts.provisions import PROVISIONS, clause_label
from dora_roi.i18n import format_date, translator
from dora_roi.reporting.env import environment

_HEADER = PatternFill("solid", fgColor="1C5CAB")
_PRIO_FILL = {"high": "F8D7D7", "medium": "FDEBC8", "low": "E3F1E3"}


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


def _header(ws: Worksheet, headers: list[str], widths: list[int]) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def _wrap(ws: Worksheet) -> None:
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.auto_filter.ref = ws.dimensions


def write_plan_workbook(plan: RemediationPlan, path: Path, *, lang: str = "en",
                        client: str | None = None) -> Path:
    """Write the remediation plan as an Excel workbook the client can work in."""
    t = translator(lang)
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Remediation plan" if lang != "de" else "Maßnahmenplan"
    _header(ws, ["#", t("g.priority"), t("g.provider"), t("g.contract"), t("g.entity"),
                 t("c30.critical_functions"), t("c30.provision"), "Art.", t("g.status"),
                 t("c30.clause"), t("c30.evidence"), t("g.action"), t("g.target"),
                 t("g.contract_end"), t("g.owner"), t("g.status") + " (client)", t("g.notes")],
            [5, 10, 30, 16, 28, 34, 40, 18, 11, 12, 48, 56, 12, 12, 18, 16, 30])
    for n, i in enumerate(plan.items, start=1):
        note = []
        if i.inherited_from:
            note.append(t("c30.inherited", ref=i.inherited_from))
        if i.applies_to:
            note.append(t("c30.applies_to", refs=", ".join(i.applies_to)))
        ws.append([n, t(f"prio.{i.priority.value}"), i.providers, i.contract_ref, i.entities,
                   i.critical_functions or "—", i.provision.title(lang), i.provision.article,
                   t(f"st.{i.status.value}"), i.clause_ref, i.evidence, i.action(lang),
                   i.target_date, i.contract_end, "", "", "; ".join(note)])
        ws.cell(ws.max_row, 2).fill = PatternFill("solid",
                                                  fgColor=_PRIO_FILL[i.priority.value])
        ws.cell(ws.max_row, 13).number_format = "yyyy-mm-dd"
        ws.cell(ws.max_row, 14).number_format = "yyyy-mm-dd"
    _wrap(ws)
    dv = DataValidation(type="list", formula1='"open,in negotiation,agreed,signed,accepted risk"',
                        allow_blank=True)
    dv.add(f"P2:P{max(ws.max_row, 2) + 200}")
    ws.add_data_validation(dv)

    prov = wb.create_sheet("By provider" if lang != "de" else "Nach Dienstleister")
    _header(prov, [t("g.provider"), t("c30.critical_functions"), t("g.contracts"),
                   t("c30.assessed"), t("c30.with_gaps"), t("st.missing"), t("st.partial"),
                   t("g.status")], [36, 14, 12, 12, 12, 10, 10, 22])
    for p in plan.portfolio.providers:
        prov.append([p.name, len(p.critical_functions), len(p.contracts), p.assessed,
                     p.with_gaps, p.missing, p.partial, t(f"cs.{p.status.value}")])
    _wrap(prov)

    todo = wb.create_sheet("To assess" if lang != "de" else "Zu bewerten")
    _header(todo, [t("g.contract"), t("g.provider"), t("g.critical"), t("g.status"),
                   t("c30.critical_functions")], [16, 36, 14, 24, 60])
    for c in plan.to_assess:
        todo.append([c.ref, c.context.provider_names,
                     t("g.yes") if c.context.critical else t("g.no"),
                     t(f"cs.{c.status.value}"),
                     "; ".join(f"{f.function_id} {f.name}" for f in c.context.critical_functions)])
    _wrap(todo)

    chk = wb.create_sheet("Checklist" if lang != "de" else "Checkliste")
    _header(chk, ["ID", "Art.", t("c30.provision"), "Scope", "Requirement", t("g.action")],
            [11, 20, 44, 10, 80, 70])
    for pr in PROVISIONS:
        chk.append([pr.id, pr.article, pr.title(lang), pr.scope.value, pr.requirement(lang),
                    pr.remediation(lang)])
    _wrap(chk)

    info = wb.create_sheet("README")
    for line in (t("c30.plan.title") + (f" – {client}" if client else ""),
                 t("g.prepared", date=format_date(plan.plan_date, lang)),
                 t("c30.method"), t("g.disclaimer"), f"dora-roi-toolkit {__version__}"):
        info.append([line])
        info.cell(info.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
    info.column_dimensions["A"].width = 120
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
