"""Audit-trail export (CSV), shared by the web app and the CLI."""

from __future__ import annotations

import csv
import io

from dora_roi.model import TEMPLATES_BY_CODE
from dora_roi.web.views import display
from dora_roi.workspace import Workspace

HEADER = ["timestamp_utc", "user", "action", "template", "row", "column", "column_label",
          "old_value", "new_value", "note"]
_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def column_label(template: str | None, column: str | None) -> str:
    if not template or not column or template not in TEMPLATES_BY_CODE:
        return column or ""
    spec = TEMPLATES_BY_CODE[template].column_by_code(column)
    return spec.label if spec else column


def csv_safe(value: object) -> str:
    """Neutralise spreadsheet formula triggers (the audit log is read by people in Excel)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in _TRIGGERS else text


def audit_csv(ws: Workspace) -> str:
    """Complete change history: who changed which field, when, old and new value."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER)
    for ch in ws.changes:
        writer.writerow([csv_safe(x) for x in (
            ch.at.isoformat(timespec="seconds"), ch.user, ch.kind, ch.template, ch.row,
            ch.column or "", column_label(ch.template, ch.column) if ch.column else "",
            display(ch.old), display(ch.new), ch.note)])
    return buf.getvalue()
