"""Concentration analysis, provider pages, renewals and register comparison."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dora_roi.diff import diff_registers
from dora_roi.graph import build_graph, chains_table, render_svg
from dora_roi.io.loader import load_raw
from dora_roi.reporting.executive import build_charts
from dora_roi.web.context import (
    ROI_SUFFIXES,
    Ctx,
)
from dora_roi.web.helpers import (
    _graph_labels,
)
from dora_roi.web.i18n import translator
from dora_roi.web.views import provider_profile, stepper
from dora_roi.workspace import EditError, Workspace

router = APIRouter()


@router.get("/w/{wid}/provider/{code}", response_class=HTMLResponse)
def provider(ctx: Ctx, request: Request, wid: str, code: str) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    t = translator(ctx.lang_of(request))
    if code not in ws.register.providers_by_code() and not any(
            p.code == code for p in ws.analysis.providers):
        raise HTTPException(status_code=404)
    profile = provider_profile(ws, code, t)
    graph = build_graph(ws.register, focus=code)
    svg = render_svg(graph, link_prefix=f"/w/{wid}/provider/",
                     labels=_graph_labels(t)) if graph.edges else None
    return ctx.ws_page(request, ws, "ws_provider.html.j2", "analyse", p=profile, graph_svg=svg,
                   chains=chains_table(ws.register, code))

@router.get("/w/{wid}/analyse", response_class=HTMLResponse)
def analyse_page(ctx: Ctx, request: Request, wid: str, color: str = "criticality",
                 critical: int = 0, isolated: int = 0) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    t = translator(ctx.lang_of(request))
    color = color if color in ("criticality", "region") else "criticality"
    graph = build_graph(ws.register, critical_only=bool(critical),
                        with_isolated=bool(isolated))
    svg = render_svg(graph, color_by=color, link_prefix=f"/w/{wid}/provider/",
                     labels=_graph_labels(t))
    return ctx.ws_page(request, ws, "ws_analyse.html.j2", "analyse", a=ws.analysis,
                   charts=build_charts(ws.analysis), graph_svg=svg, color=color,
                   critical=critical, isolated=isolated, chains=chains_table(ws.register))

@router.get("/w/{wid}/renewals", response_class=HTMLResponse)
def renewals(ctx: Ctx, request: Request, wid: str, critical: int = 0) -> HTMLResponse:
    from dora_roi.analytics.renewals import notice_schedule

    ws = ctx.ws_or_404(wid)
    items = notice_schedule(ws.register)
    if critical:
        items = [i for i in items if i.critical]
    return ctx.ws_page(request, ws, "ws_renewals.html.j2", "analyse", items=items,
                   critical=critical)

@router.get("/w/{wid}/compare", response_class=HTMLResponse)
def compare(ctx: Ctx, request: Request, wid: str, other: str | None = None,
            version: int | None = None, all: int = 0) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    result = None
    label = None
    if other:
        o = ctx.ws_or_404(other)
        result = diff_registers(o.register, ws.register, o.name, ws.name)
        label = o.name
    elif version is not None:
        try:
            old = ws.register_at(version)
        except EditError as exc:
            raise HTTPException(status_code=404) from exc
        result = diff_registers(old, ws.register, f"v{version}", ws.name)
        label = f"v{version}"
    others = [w for w in ctx.my_workspaces() if w.id != ws.id]
    return ctx.ws_page(request, ws, "ws_compare.html.j2", "analyse", result=result, label=label,
                   others=others, other=other, version=version, show_all=bool(all))

@router.post("/w/{wid}/compare")
async def compare_upload(ctx: Ctx, request: Request, wid: str,
                         file: Annotated[UploadFile, File()]) -> Response:
    ws = ctx.ws_or_404(wid)
    got = await ctx.read_upload(file, ROI_SUFFIXES)
    if isinstance(got, str):
        return ctx.upload_error(request, got, "ws_compare.html.j2", ws=ws,
                            steps=stepper(ws, "analyse"), step="analyse",
                            quality=ws.quality, counts=ws.report.severity_counts(),
                            result=None, others=[], other=None, version=None, label=None,
                            show_all=False)
    name, data = got

    def build() -> Workspace:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"previous{Path(name).suffix.lower()}"
            path.write_bytes(data)
            raw, _ = load_raw(path)
        raw.source = name
        return ctx.own(Workspace(name, raw, source=name), request)

    try:
        other = await ctx.offload(build)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=type(exc).__name__) from exc
    return RedirectResponse(f"/w/{wid}/compare?other={other.id}", status_code=303)
