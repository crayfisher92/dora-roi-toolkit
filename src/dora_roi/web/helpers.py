"""Small response and formatting helpers shared by the routers."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import Response

from dora_roi.audit import column_label
from dora_roi.io.limits import InputTooLargeError
from dora_roi.validation import Finding
from dora_roi.web.auth import CURRENT_USER
from dora_roi.web.views import display
from dora_roi.workspace import DEFAULT_USER, EditError, Workspace

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _download(data: bytes, filename: str, media_type: str) -> Response:
    return Response(data, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def user_of(request: Request) -> str:
    """Name recorded in the audit trail: the signed-in user, else the self-declared name."""
    return CURRENT_USER.get() or clean_user(request.cookies.get("roi_user", "")) \
        or DEFAULT_USER


def clean_user(name: str) -> str:
    """Printable, trimmed user name (max 80 characters) for the audit trail."""
    return "".join(ch for ch in name if ch.isprintable()).strip()[:80]


def _reason(exc: Exception) -> str:
    return str(exc) if isinstance(exc, InputTooLargeError) else type(exc).__name__


_column_label = column_label


def _raw_value(ws: Workspace, f: Finding) -> str:
    if not (f.template and f.row and f.column):
        return ""
    try:
        return display(ws.row(f.template, f.row).values.get(f.column))
    except EditError:
        return ""


def _provider_link(ws: Workspace) -> Any:
    codes = set(ws.register.providers_by_code())

    def link(value: Any) -> str | None:
        text = display(value)
        return f"/w/{ws.id}/provider/{text}" if text in codes else None

    return link


def _graph_labels(t: Any) -> dict[str, str]:
    return {"title": t("an.graph"), "critical": t("an.legend.critical"),
            "empty": t("fix.none")}


def _state_json(ws: Workspace, template: str, row: int, column: str, changed: bool,
                t: Any) -> dict[str, Any]:
    q = ws.quality
    counts = ws.report.severity_counts()
    remaining = [f for f in ws.findings_for(template, row) if f.column == column]
    return {
        "ok": True,
        "changed": changed,
        "value": display(ws.row(template, row).values.get(column)),
        "resolved": not remaining,
        "findings": [{"rule_id": f.rule_id, "severity": f.severity.value,
                      "message": f.message} for f in remaining],
        "counts": counts,
        "score": q.score,
        "readiness": q.readiness.value,
        "readiness_label": t(f"ready.{q.readiness.value}"),
        "message": t("fix.saved", errors=counts["error"], warnings=counts["warning"])
        if changed else t("fix.unchanged"),
    }
