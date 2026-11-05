"""Render a :class:`ValidationReport` as JSON, Markdown, HTML or plain text."""

from __future__ import annotations

import json
from enum import StrEnum

from dora_roi.reporting.env import environment
from dora_roi.validation import ValidationReport
from dora_roi.validation.findings import RULES, Finding

MAX_HTML_FINDINGS = 5000
MAX_PDF_FINDINGS = 1000  # ~35 pages; rendering time grows with page count


class ReportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "md"
    HTML = "html"
    TEXT = "text"


def render_json(report: ValidationReport) -> str:
    return json.dumps(report.to_json_dict(), indent=2, ensure_ascii=False)


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: ValidationReport, max_findings: int = 1000) -> str:
    counts = report.severity_counts()
    status = "✅ PASSED" if report.passed else "❌ FAILED"
    lines = [
        "# DORA Register of Information – validation report",
        "",
        f"- **Entity:** {report.maintainer_name or '—'} (`{report.maintainer_lei or '—'}`)",
        f"- **Reference date:** {report.reference_date or '—'}",
        f"- **Source:** {report.source or '—'}",
        f"- **Generated:** {report.generated_at:%Y-%m-%d %H:%M} UTC "
        f"(dora-roi-toolkit {report.toolkit_version}, {report.rules_run} rules)",
        "",
        f"**Result: {status}** — {counts['error']} error(s), {counts['warning']} warning(s), "
        f"{counts['info']} info.",
        "",
        "## Findings by rule",
        "",
    ]
    by_rule = report.by_rule()
    if by_rule:
        lines += ["| Rule | Severity | Title | Count | Supports |", "|---|---|---|---:|---|"]
        for rule, n in by_rule:
            lines.append(f"| `{rule.id}` | {rule.severity.value} | {_md_escape(rule.title)} | {n} "
                         f"| {_md_escape('; '.join(rule.references))} |")
    else:
        lines.append("_No findings._")
    lines += ["", "## Findings by template", "",
              "| Template | Records | Errors | Warnings | Info |", "|---|---:|---:|---:|---:|"]
    bt = report.by_template()
    for code, n in report.record_counts.items():
        c = bt.get(code, {})
        lines.append(f"| {code} | {n} | {c.get('error', 0)} | {c.get('warning', 0)} | "
                     f"{c.get('info', 0)} |")
    if "register" in bt:
        c = bt["register"]
        lines.append(f"| register / import | — | {c['error']} | {c['warning']} | {c['info']} |")

    findings = report.sorted_findings()
    lines += ["", "## Findings", ""]
    if findings:
        lines += ["| Severity | Rule | Location | Record | Message |", "|---|---|---|---|---|"]
        for f in findings[:max_findings]:
            lines.append(f"| {f.severity.value} | `{f.rule_id}` | {f.location} | "
                         f"{_md_escape(f.record_key or '')} | {_md_escape(f.message)} |")
        if len(findings) > max_findings:
            lines += ["", f"_… {len(findings) - max_findings} more findings omitted; see the "
                      "JSON report._"]
    else:
        lines.append("_No findings._")
    if report.accepted:
        lines += ["", "## Accepted findings", "",
                  "| Rule | Location | Message | Justification |", "|---|---|---|---|"]
        lines += [f"| `{f.rule_id}` | {f.location} | {_md_escape(f.message)} | "
                  f"{_md_escape(f.accepted_reason or '')} |" for f in report.accepted]
    if report.rule_failures:
        lines += ["", "## Rule failures", ""]
        lines += [f"- `{rf.rule_id}`: {rf.error}" for rf in report.rule_failures]
    lines += ["", "---", "_Not an official EBA/ESA tool; see docs/ASSUMPTIONS.md._", ""]
    return "\n".join(lines)


def render_html(report: ValidationReport, *, pdf: bool = False) -> str:
    """HTML report; ``pdf=True`` renders the print variant (details open, no script, fewer
    rows – the JSON report always has every finding)."""
    findings = report.sorted_findings()
    limit = MAX_PDF_FINDINGS if pdf else MAX_HTML_FINDINGS
    template = environment().get_template("validation.html.j2")
    return template.render(
        report=report,
        findings=findings[:limit],
        truncated=len(findings) > limit,
        pdf=pdf,
    )


FINDINGS_XLSX_HEADER = ("Severity", "Rule", "Title", "Template", "Row", "Column", "Column label",
                        "Record", "Value", "Message", "Why it matters", "Regulation",
                        "Owner", "Status", "Comment")


def render_xlsx(report: ValidationReport, lang: str = "en") -> bytes:
    """Findings as a workbook to hand to business owners (one row per finding, with
    explanation and regulation reference, plus empty Owner/Status/Comment columns for
    tracking). Accepted findings are on a second sheet with their justification."""
    import io

    import xlsxwriter

    from dora_roi.explain import explain, rule_title
    from dora_roi.model import TEMPLATES_BY_CODE

    def column_label(template: str | None, column: str | None) -> str:
        model = TEMPLATES_BY_CODE.get(template or "")
        spec = model.column_by_code(column) if model and column else None
        return spec.label if spec else (column or "")

    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "strings_to_formulas": False,
                                   "strings_to_numbers": False, "strings_to_urls": False})
    head = wb.add_format({"bold": True, "bg_color": "#1C5CAB", "font_color": "#FFFFFF",
                          "text_wrap": True, "valign": "top"})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})
    quoted = wb.add_format({"text_wrap": True, "valign": "top", "quote_prefix": True})

    def sheet(name: str, findings: list[Finding], extra: str | None) -> None:
        ws = wb.add_worksheet(name)
        header = (*FINDINGS_XLSX_HEADER[:12], extra) if extra else FINDINGS_XLSX_HEADER
        for c, h in enumerate(header):
            ws.write_string(0, c, h, head)
        for r, f in enumerate(findings, start=1):
            rule = RULES.get(f.rule_id)
            values: list[object] = [
                f.severity.value, f.rule_id, rule_title(f.rule_id, lang), f.template or "",
                f.row, f.column or "", column_label(f.template, f.column), f.record_key or "",
                f.value or "", f.message, explain(f.rule_id, lang),
                "; ".join(rule.references) if rule else ""]
            if extra:
                values.append(f.accepted_reason or "")
            for c, v in enumerate(values):
                if isinstance(v, int):
                    ws.write_number(r, c, v)
                elif v:
                    text = str(v)
                    ws.write_string(r, c, text, quoted if text[:1] in "=+-@\t\r" else wrap)
        widths = (9, 9, 34, 9, 6, 8, 28, 30, 18, 50, 50, 28, 16, 12, 30)
        for c, w in enumerate(widths[:len(header)]):
            ws.set_column(c, c, w)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, max(len(findings), 1), len(header) - 1)

    sheet("Findings", report.sorted_findings(), None)
    if report.accepted:
        sheet("Accepted", report.accepted, "Justification")
    wb.close()
    return buf.getvalue()


def render_pdf(report: ValidationReport) -> bytes:
    """PDF validation report (needs the optional WeasyPrint dependency)."""
    from dora_roi.reporting.pdf import html_to_pdf

    return html_to_pdf(render_html(report, pdf=True))


def render_text(report: ValidationReport, max_findings: int = 50) -> str:
    counts = report.severity_counts()
    head = (f"{'PASSED' if report.passed else 'FAILED'}: {counts['error']} error(s), "
            f"{counts['warning']} warning(s), {counts['info']} info "
            f"[{report.rules_run} rules, reference date {report.reference_date}]")
    lines = [head]
    findings = report.sorted_findings()
    for f in findings[:max_findings]:
        lines.append(f"  {f.severity.value.upper():7} {f.rule_id:8} {f.location:28} {f.message}")
    if len(findings) > max_findings:
        lines.append(f"  … {len(findings) - max_findings} more (use --format json/md/html)")
    return "\n".join(lines)


def render(report: ValidationReport, fmt: ReportFormat | str) -> str:
    fmt = ReportFormat(fmt)
    if fmt is ReportFormat.JSON:
        return render_json(report)
    if fmt is ReportFormat.MARKDOWN:
        return render_markdown(report)
    if fmt is ReportFormat.HTML:
        return render_html(report)
    return render_text(report)
