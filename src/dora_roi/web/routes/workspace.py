"""Workspace overview, fixing, register editing, acceptances, close/share."""

from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from dora_roi.fixes import bulk_groups, findings_by_template, suggest
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE
from dora_roi.project import save_project
from dora_roi.validation import Finding, finding_key
from dora_roi.web.context import (
    FIX_GROUP_LIMIT,
    PAGE_SIZE,
    Ctx,
)
from dora_roi.web.helpers import (
    _column_label,
    _provider_link,
    _raw_value,
    _state_json,
    user_of,
)
from dora_roi.web.i18n import translator
from dora_roi.web.security import (
    safe_next,
)
from dora_roi.web.spaces import (
    PRIVATE,
    TEAM,
    file_stamp,
    unique_path,
)
from dora_roi.web.views import display
from dora_roi.workspace import Change, EditError

router = APIRouter()


@router.get("/w/{wid}", response_class=HTMLResponse)
def overview(ctx: Ctx, request: Request, wid: str) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    can_share = (ctx.autosave and ctx.spaces.team_mode and ws.session.space == PRIVATE
                 and ws.session.project_path is not None and ws.session.read_only is None)
    return ctx.ws_page(request, ws, "ws_overview.html.j2", "import",
                   notes=ws.import_notes, can_share=can_share)

@router.get("/w/{wid}/fix", response_class=HTMLResponse)
def fix(ctx: Ctx, request: Request, wid: str, template: str | None = None,
        severity: str | None = None, rule: str | None = None) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    findings = ws.report.sorted_findings()
    grouped = findings_by_template(findings)
    if template is None and grouped:
        template = next(iter(grouped))
    selected = [f for f in findings if (f.template or "register") == template
                and (severity is None or f.severity.value == severity)
                and (rule is None or f.rule_id == rule)]
    by_sev: dict[str, dict[str, list[Finding]]] = {}
    for f in selected:
        by_sev.setdefault(f.severity.value, {}).setdefault(f.rule_id, []).append(f)
    bulks = [b for b in bulk_groups(selected) if b.count >= 2]
    return ctx.ws_page(request, ws, "ws_fix.html.j2", "fix", grouped=grouped,
                   template=template, by_sev=by_sev, severity=severity, rule=rule,
                   bulks=bulks, suggest=suggest, limit=FIX_GROUP_LIMIT,
                   column_label=_column_label, raw_value=lambda f: _raw_value(ws, f))

@router.post("/w/{wid}/cell")
async def edit_cell(ctx: Ctx, request: Request, wid: str) -> Response:
    ws = ctx.ws_for_edit(wid)
    form = await request.form()
    template = str(form.get("template", ""))
    column = str(form.get("column", ""))
    value = str(form.get("value", ""))
    user = user_of(request)

    def apply(row: int) -> Change | None:
        change = ws.edit(template, row, column, value, user=user)
        ws.report  # noqa: B018 - re-validate in the worker thread
        return change

    try:
        row = int(str(form.get("row", "")))
        change = await ctx.offload(lambda: apply(row))
    except (ValueError, EditError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(_state_json(ws, template, row, column, change is not None,
                                        translator(ctx.lang_of(request))))
    target = safe_next(str(form.get("next", "")), f"/w/{wid}/fix")
    return RedirectResponse(target, status_code=303)

@router.post("/w/{wid}/bulk")
async def bulk(ctx: Ctx, request: Request, wid: str) -> Response:
    ws = ctx.ws_for_edit(wid)
    form = await request.form()
    rows = [int(x) for x in str(form.get("rows", "")).split(",") if x.strip().isdigit()]
    user = user_of(request)

    def apply() -> None:
        ws.bulk_replace(str(form.get("template", "")), str(form.get("column", "")),
                        str(form.get("old", "")), str(form.get("new", "")), rows or None,
                        user=user)
        ws.report  # noqa: B018 - re-validate in the worker thread

    try:
        await ctx.offload(apply)
    except EditError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(safe_next(str(form.get("next", "")), f"/w/{wid}/fix"),
                            status_code=303)

@router.get("/w/{wid}/register", response_class=HTMLResponse)
def register_root(ctx: Ctx, wid: str) -> Response:
    return RedirectResponse(f"/w/{wid}/register/B_01.01", status_code=303)

@router.get("/w/{wid}/register/{template}", response_class=HTMLResponse)
def register_table(ctx: Ctx, request: Request, wid: str, template: str, q: str = "",
                   issues: int = 0, page: int = 1) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    if template not in TEMPLATES_BY_CODE:
        raise HTTPException(status_code=404)
    model = TEMPLATES_BY_CODE[template]
    flagged = ws.rows_with_findings(template)
    rows = ws.table(template).rows
    needle = q.strip().casefold()
    if needle:
        rows = [r for r in rows if any(needle in display(v).casefold()
                                       for v in r.values.values())]
    if issues:
        rows = [r for r in rows if r.row in flagged]
    pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = min(max(page, 1), pages)
    shown = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    counts = {m.TEMPLATE: len(ws.table(m.TEMPLATE).rows) for m in TEMPLATE_MODELS}
    return ctx.ws_page(request, ws, "ws_register.html.j2", "fix", template=template, model=model,
                   rows=shown, total=len(rows), flagged=flagged, q=q, issues=issues,
                   page=page, pages=pages, table_counts=counts,
                   provider_link=_provider_link(ws))

@router.get("/w/{wid}/register/{template}/{row}", response_class=HTMLResponse)
def register_row(ctx: Ctx, request: Request, wid: str, template: str, row: int) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    try:
        raw_row = ws.row(template, row)
    except EditError as exc:
        raise HTTPException(status_code=404) from exc
    findings = ws.findings_for(template, row)
    return ctx.ws_page(request, ws, "ws_row.html.j2", "fix", template=template,
                   model=TEMPLATES_BY_CODE[template], raw_row=raw_row, findings=findings,
                   by_column={f.column: f for f in findings if f.column}, suggest=suggest)

@router.post("/w/{wid}/register/{template}/{row}")
async def register_row_save(ctx: Ctx, request: Request, wid: str, template: str, row: int
                            ) -> Response:
    ws = ctx.ws_for_edit(wid)
    form = await request.form()
    user = user_of(request)
    if form.get("delete"):
        try:
            await ctx.offload(lambda: ws.delete_row(template, row, user=user))
        except EditError as exc:
            raise HTTPException(status_code=404) from exc
        return RedirectResponse(f"/w/{wid}/register/{template}", status_code=303)

    def apply() -> None:
        raw_row = ws.row(template, row)
        for spec in TEMPLATES_BY_CODE[template].columns():
            if spec.code in form:
                new = str(form.get(spec.code, ""))
                if display(raw_row.values.get(spec.code)) != new.strip():
                    ws.edit(template, row, spec.code, new, user=user)
        ws.report  # noqa: B018 - re-validate in the worker thread

    try:
        await ctx.offload(apply)
    except (EditError, KeyError) as exc:
        raise HTTPException(status_code=404) from exc
    return RedirectResponse(f"/w/{wid}/register/{template}/{row}?saved=1", status_code=303)

@router.post("/w/{wid}/register/{template}")
def register_add(ctx: Ctx, request: Request, wid: str, template: str) -> Response:
    ws = ctx.ws_for_edit(wid)
    try:
        row = ws.add_row(template, user=user_of(request))
    except EditError as exc:
        raise HTTPException(status_code=404) from exc
    return RedirectResponse(f"/w/{wid}/register/{template}/{row}", status_code=303)

@router.post("/w/{wid}/accept")
async def accept(ctx: Ctx, request: Request, wid: str) -> Response:
    ws = ctx.ws_for_edit(wid)
    form = await request.form()
    key = str(form.get("key", ""))
    finding = next((f for f in ws.report.findings if finding_key(f) == key), None)
    if finding is None:
        raise HTTPException(status_code=404)
    reason, user = str(form.get("reason", "")), user_of(request)
    try:
        await ctx.offload(lambda: ws.accept(finding, reason, user=user))
    except EditError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(safe_next(str(form.get("next", "")), f"/w/{wid}/fix"),
                            status_code=303)

@router.post("/w/{wid}/unaccept")
async def unaccept(ctx: Ctx, request: Request, wid: str) -> Response:
    ws = ctx.ws_for_edit(wid)
    form = await request.form()
    key, user = str(form.get("key", "")), user_of(request)
    try:
        await ctx.offload(lambda: ws.unaccept(key, user=user))
    except EditError as exc:
        raise HTTPException(status_code=404) from exc
    return RedirectResponse(safe_next(str(form.get("next", "")), f"/w/{wid}/fix"),
                            status_code=303)

@router.post("/w/{wid}/close")
def close(ctx: Ctx, wid: str) -> Response:
    """Release the edit lock and drop the workspace from memory (the file stays)."""
    ws = ctx.ws_or_404(wid)
    ctx.release_lock(ws)
    ctx.workspaces.remove(wid)
    return RedirectResponse("/", status_code=303)

@router.post("/w/{wid}/share")
def share(ctx: Ctx, wid: str) -> Response:
    """Move a project from the user's private space to the team space."""
    ws = ctx.ws_for_edit(wid)
    old = ws.session.project_path
    team = ctx.spaces.folder(TEAM, "")
    if not (ctx.autosave and ws.session.space == PRIVATE and old is not None and team is not None):
        raise HTTPException(status_code=404)
    new = unique_path(team, old.stem)
    with ws.lock:
        save_project(ws, new)
        ctx.locks.release(old, ws.id)
        ctx.locks.acquire(new, ws.id, ws.session.owner_label)
        ws.session.project_path, ws.session.space = new, TEAM
        ws.session.project_stamp = file_stamp(new)
        old.unlink(missing_ok=True)
    ws.session.notices.append(("ws.notice.shared", {"file": new.name}))
    return RedirectResponse(f"/w/{wid}", status_code=303)

@router.get("/w/{wid}/audit", response_class=HTMLResponse)
def audit(ctx: Ctx, request: Request, wid: str) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    return ctx.ws_page(request, ws, "ws_audit.html.j2", "fix",
                   entries=list(reversed(ws.changes)), column_label=_column_label)

@router.get("/w/{wid}/versions", response_class=HTMLResponse)
def versions(ctx: Ctx, request: Request, wid: str) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    return ctx.ws_page(request, ws, "ws_versions.html.j2", "fix")

@router.get("/api/w/{wid}")
def api_summary(ctx: Ctx, wid: str) -> JSONResponse:
    ws = ctx.ws_or_404(wid)
    q = ws.quality
    return JSONResponse({"id": ws.id, "name": ws.name, "score": q.score,
                         "readiness": q.readiness.value,
                         "counts": ws.report.severity_counts(),
                         "records": ws.report.record_counts})
