"""Export page and downloads (project, workbooks, xBRL-CSV, reports)."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from dora_roi.audit import audit_csv
from dora_roi.io.csv_folder import register_to_csv_texts
from dora_roi.io.excel import write_raw_workbook
from dora_roi.io.xbrl_csv import XbrlCsvOptions, build_package_files, package_name
from dora_roi.project import SUFFIX as PROJECT_SUFFIX
from dora_roi.project import save_project
from dora_roi.reporting import render_html, render_json, render_markdown
from dora_roi.reporting.executive import render_executive_summary
from dora_roi.reporting.pdf import PdfBusyError, html_to_pdf, pdf_available
from dora_roi.reporting.validation_report import render_xlsx
from dora_roi.web.context import (
    EXPORT_LABELS,
    Ctx,
)
from dora_roi.web.helpers import (
    XLSX,
    _download,
    user_of,
)
from dora_roi.workspace import Workspace

router = APIRouter()


@router.get("/w/{wid}/export", response_class=HTMLResponse)
def export_page(ctx: Ctx, request: Request, wid: str) -> HTMLResponse:
    ws = ctx.ws_or_404(wid)
    package_errors = len(ws.dora_report().errors) if ws.out_of_scope else None
    return ctx.ws_page(request, ws, "ws_export.html.j2", "export", pdf=pdf_available(),
                       package_errors=package_errors)

@router.get("/w/{wid}/download/{kind}")
def download(ctx: Ctx, request: Request, wid: str, kind: str) -> Response:
    ws = ctx.ws_or_404(wid)
    if kind not in EXPORT_LABELS:
        raise HTTPException(status_code=404)
    user = user_of(request)
    response = render_download(ws, kind, user, ctx.lang_of(request))
    if kind == "xbrl" and ws.out_of_scope:  # the package is the submission view (D-084)
        ws.record_export(f"{EXPORT_LABELS[kind]} without {len(ws.out_of_scope)} "
                         "entit(y/ies) outside the DORA scope", user=user,
                         report=ws.dora_report())
    else:
        ws.record_export(EXPORT_LABELS[kind], user=user)  # audit trail: who exported what
    return response

def render_download(ws: Workspace, kind: str, user: str, lang: str) -> Response:
    stem = Path(ws.name).stem.replace(" ", "_") or "register"
    if kind == "project":
        with tempfile.TemporaryDirectory() as tmp:
            data = save_project(ws, Path(tmp) / f"p{PROJECT_SUFFIX}").read_bytes()
        return _download(data, f"{stem}{PROJECT_SUFFIX}", "application/vnd.sqlite3")
    if kind == "xlsx":
        with tempfile.TemporaryDirectory() as tmp, ws.lock:
            data = write_raw_workbook(ws.raw, Path(tmp) / "r.xlsx").read_bytes()
        return _download(data, f"{stem}-corrected.xlsx", XLSX)
    if kind == "csv":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, text in register_to_csv_texts(ws.export_register()).items():
                zf.writestr(name, text)
        return _download(buf.getvalue(), f"{stem}-csv.zip", "application/zip")
    if kind == "xbrl":
        options = XbrlCsvOptions()
        dora = ws.dora_register()  # entities outside the DORA scope are left out (P-15)
        pkg = package_name(dora, options)
        files, _ = build_package_files(dora, options)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, text in files.items():
                zf.writestr(f"{pkg}/{rel}", text)
        return _download(buf.getvalue(), f"{pkg}.zip", "application/zip")
    if kind == "validation.html":
        return HTMLResponse(render_html(ws.report))
    if kind == "validation.md":
        return _download(render_markdown(ws.report).encode(), f"{stem}-validation.md",
                         "text/markdown")
    if kind == "validation.xlsx":
        return _download(render_xlsx(ws.report, lang), f"{stem}-findings.xlsx", XLSX)
    if kind == "validation.json":
        return Response(render_json(ws.report), media_type="application/json")
    if kind == "executive.html":
        return HTMLResponse(render_executive_summary(ws.register, ws.report,
                                                     analysis=ws.analysis,
                                                     prepared_by=user))
    if kind in ("executive.pdf", "validation.pdf"):
        if not pdf_available():
            raise HTTPException(status_code=404, detail="PDF export is not installed")
        if kind == "executive.pdf":
            html = render_executive_summary(ws.register, ws.report, analysis=ws.analysis,
                                            prepared_by=user, pdf=True)
        else:
            html = render_html(ws.report, pdf=True)
        name = f"{stem}-{kind.replace('.pdf', '')}.pdf"
        try:
            data = html_to_pdf(html)
        except PdfBusyError as exc:
            raise HTTPException(status_code=503, detail=str(exc),
                                headers={"Retry-After": "10"}) from exc
        return _download(data, name, "application/pdf")
    if kind == "analysis.json":
        return JSONResponse(ws.analysis.model_dump(mode="json"))
    if kind == "audit.csv":
        return _download(audit_csv(ws).encode("utf-8-sig"), f"{stem}-audit-log.csv",
                         "text/csv")
    raise HTTPException(status_code=404)
