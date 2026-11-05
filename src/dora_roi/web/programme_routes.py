"""Workbench screens that combine the programme modules: the FINMA mapping (Swiss angle),
the DORA readiness dashboard and the readiness report for a CRO."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dora_roi.contracts.analysis import remediation_plan
from dora_roi.finma import OPRISK, OUTSOURCING, evaluate_finma
from dora_roi.incidents.report import overview
from dora_roi.model.refdata import country_name
from dora_roi.quality import quality_score
from dora_roi.readiness import ReadinessView, build_readiness, render_readiness_html
from dora_roi.reporting.pdf import PdfBusyError, html_to_pdf, pdf_available
from dora_roi.scope import restrict_to_scope
from dora_roi.web.context import Ui, download, stem
from dora_roi.workspace import Workspace

CIRCULARS = ((OUTSOURCING, "FINMA Circular 2018/3 – Outsourcing"),
             (OPRISK, "FINMA Circular 2023/1 – Operational risks and resilience (banks)"))


def workspace_readiness(ws: Workspace, lang: str, now: datetime | None = None
                        ) -> ReadinessView:
    """The readiness view of a workspace (register, assessments, incidents, FINMA)."""
    moment = now or datetime.now(UTC)
    portfolio = ws.portfolio
    ref = ws.register.reference_date
    plan = remediation_plan(portfolio, max(ref, date.today()) if ref else date.today())
    report = ws.dora_report()  # the submission: entities outside the DORA scope excluded
    return build_readiness(
        report=report, quality=ws.quality if report is ws.report else quality_score(report),
        analysis=ws.analysis, portfolio=portfolio,
        plan=plan, incidents=overview(ws.incidents, ws.register, moment),
        finma=evaluate_finma(ws.register, portfolio, ws.incidents, moment), lang=lang,
        now=moment, register=ws.register,
        out_of_scope=len(ws.out_of_scope) if report is not ws.report else 0)


def pdf_response(html: str, filename: str) -> Response:
    """The report as PDF (WeasyPrint); 404 when PDF support is not installed."""
    if not pdf_available():
        raise HTTPException(status_code=404, detail="PDF export is not available")
    try:
        data = html_to_pdf(html)
    except PdfBusyError as exc:  # concurrency limit of the base's PDF pipeline (B-31)
        raise HTTPException(status_code=503, detail=str(exc),
                            headers={"Retry-After": "10"}) from exc
    return download(data, filename, "application/pdf")


def register(app: FastAPI, ui: Ui) -> None:
    @app.get("/w/{wid}/finma", response_class=HTMLResponse)
    def finma(request: Request, wid: str, scope_saved: int = 0) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        view = evaluate_finma(ws.register, ws.portfolio, ws.incidents)
        maintainer = ws.register.maintainer.lei if ws.register.maintainer else None
        _, summary = restrict_to_scope(ws.register, ws.out_of_scope - {maintainer or ""})
        return ui.ws_page(request, ws, "ws_finma.html.j2", "programme", view=view,
                          circulars=CIRCULARS, country_name=country_name,
                          entities=ws.register.b_01_02, maintainer=maintainer,
                          scope_summary=summary, scope_saved=scope_saved)

    @app.post("/w/{wid}/scope")
    async def scope(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        form = await request.form()
        known = {e.lei for e in ws.register.b_01_02 if e.lei}
        chosen = {v for v in form.getlist("out") if isinstance(v, str) and v in known}
        maintainer = ws.register.maintainer.lei if ws.register.maintainer else None
        chosen.discard(maintainer or "")
        if chosen != ws.out_of_scope:
            with ws.lock:
                ws.out_of_scope = chosen
                ws.programme_changed("scope", "B_01.02", "Outside the DORA scope: "
                                     + (", ".join(sorted(chosen)) or "none"),
                                     ui.user_of(request))
        return RedirectResponse(f"/w/{wid}/finma?scope_saved=1#h-scope", status_code=303)

    @app.get("/w/{wid}/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        return ui.ws_page(request, ws, "ws_dashboard.html.j2", "programme",
                          rd=workspace_readiness(ws, ui.lang_of(request)),
                          pdf=pdf_available())

    def readiness_html(request: Request, ws: Workspace) -> str:
        lang = ui.lang_of(request)
        return render_readiness_html(workspace_readiness(ws, lang), lang=lang,
                                     client=ws.report.maintainer_name or ws.name,
                                     prepared_by=ui.user_of(request))

    @app.get("/w/{wid}/readiness.html", response_class=HTMLResponse)
    def readiness_report(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        response = HTMLResponse(readiness_html(request, ws))
        ui.audit_export(request, ws, "DORA readiness report (HTML)")
        return response

    @app.get("/w/{wid}/readiness.pdf")
    def readiness_pdf(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        response = pdf_response(readiness_html(request, ws), f"{stem(ws)}-dora-readiness.pdf")
        ui.audit_export(request, ws, "DORA readiness report (PDF)")
        return response
