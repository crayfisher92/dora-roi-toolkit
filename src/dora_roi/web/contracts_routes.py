"""Workbench screens for the DORA Art. 30 contract gap analysis.

* ``/w/{id}/contracts`` – portfolio: providers by criticality, arrangements with their
  compliance status, downloads (remediation plan HTML/Excel, assessments JSON/Excel), import;
* ``/w/{id}/contracts/checklist`` – the checklist with article references;
* ``/w/{id}/contract/{ref}`` – assess one arrangement (B_02.01 record): per provision
  present / partial / missing, clause reference and evidence; optional upload of the contract
  (PDF/DOCX/TXT) to pre-fill *suggestions* that the reviewer confirms before saving.
"""

from __future__ import annotations

import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from dora_roi.contracts.analysis import (
    ComplianceStatus,
    ContractContext,
    contract_contexts,
    evaluate_contract,
    gaps_by_provision,
    remediation_plan,
)
from dora_roi.contracts.consistency import consistency_hints
from dora_roi.contracts.extract import ExtractionError, extract_text, pdf_supported
from dora_roi.contracts.model import (
    AssessmentBook,
    ContractAssessment,
    ProvisionStatus,
    RemediationProgress,
    read_assessment_workbook,
    write_assessment_workbook,
)
from dora_roi.contracts.provisions import PROVISIONS, Scope, applicable
from dora_roi.contracts.report import render_plan_html, write_plan_workbook
from dora_roi.contracts.suggest import SuggestionResult, apply_suggestions, suggest
from dora_roi.reporting.pdf import pdf_available as pdf_available_
from dora_roi.sample.contract_docs import (
    SAMPLE_CONTRACT_NAME,
    SAMPLE_CONTRACT_REF,
    SAMPLE_CONTRACT_TEXT,
    docx_bytes,
)
from dora_roi.web.context import XLSX, Ui, download, form_text, stem
from dora_roi.workspace import DEFAULT_USER, Workspace

DOC_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
ASSESSMENT_SUFFIXES = {".json", ".xlsx", ".xlsm"}
STATUS_FILTERS = ("all", "gaps", "not_assessed", "incomplete", "exception", "compliant")


def contract_url(wid: str, ref: str) -> str:
    return f"/w/{wid}/contract/{quote(ref, safe='')}"


def _plan(ws: Workspace) -> Any:
    ref = ws.register.reference_date
    return remediation_plan(ws.portfolio, date.today() if ref is None else max(ref, date.today()))


def register(app: FastAPI, ui: Ui) -> None:
    @app.get("/w/{wid}/contracts", response_class=HTMLResponse)
    def contracts(request: Request, wid: str, status: str = "all", critical: int = 0,
                  q: str = "", imported: int = -1, problems: int = 0,
                  updated: int = 0) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        pf = ws.portfolio
        status = status if status in STATUS_FILTERS else "all"
        needle = q.strip().casefold()
        rows = [c for c in pf.contracts
                if (status == "all" or c.status.value == status)
                and (not critical or c.context.critical)
                and (not needle or needle in c.ref.casefold()
                     or needle in c.context.provider_names.casefold())]
        return ui.ws_page(request, ws, "ws_contracts.html.j2", "programme", pf=pf, rows=rows,
                          status_filter=status, critical=critical, q=q, plan=_plan(ws),
                          by_provision=gaps_by_provision(pf), filters=STATUS_FILTERS,
                          imported=imported, problems=problems, updated=updated,
                          contract_url=contract_url,
                          pdf=pdf_available_())

    @app.get("/w/{wid}/contracts/checklist", response_class=HTMLResponse)
    def checklist(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        return ui.ws_page(request, ws, "ws_checklist.html.j2", "programme",
                          provisions=PROVISIONS, Scope=Scope)

    def plan_page(request: Request, ws: Workspace) -> str:
        return render_plan_html(_plan(ws), lang=ui.lang_of(request),
                                client=ws.report.maintainer_name or ws.name,
                                prepared_by=ui.user_of(request))

    @app.get("/w/{wid}/contracts/plan.html", response_class=HTMLResponse)
    def plan_html(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        response = HTMLResponse(plan_page(request, ws))
        ui.audit_export(request, ws, "Art. 30 remediation plan (HTML)")
        return response

    @app.get("/w/{wid}/contracts/plan.pdf")
    def plan_pdf(request: Request, wid: str) -> Response:
        from dora_roi.web.programme_routes import pdf_response

        ws = ui.ws_or_404(wid)
        response = pdf_response(plan_page(request, ws), f"{stem(ws)}-art30-remediation-plan.pdf")
        ui.audit_export(request, ws, "Art. 30 remediation plan (PDF)")
        return response

    @app.get("/w/{wid}/contracts/plan.xlsx")
    def plan_xlsx(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        with tempfile.TemporaryDirectory() as tmp:
            data = write_plan_workbook(_plan(ws), Path(tmp) / "plan.xlsx",
                                       lang=ui.lang_of(request),
                                       client=ws.report.maintainer_name).read_bytes()
        ui.audit_export(request, ws, "Art. 30 remediation plan (Excel)")
        return download(data, f"{stem(ws)}-art30-remediation-plan.xlsx", XLSX)

    @app.get("/w/{wid}/contracts/assessments.json")
    def assessments_json(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        ui.audit_export(request, ws, "Art. 30 assessments (JSON)")
        return download(ws.contracts.to_json().encode(), f"{stem(ws)}-art30-assessments.json",
                        "application/json")

    @app.get("/w/{wid}/contracts/assessments.xlsx")
    def assessments_xlsx(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        ui.audit_export(request, ws, "Art. 30 assessments (Excel)")
        refs = {r: c.critical for r, c in contract_contexts(ws.register).items()}
        with tempfile.TemporaryDirectory() as tmp:
            data = write_assessment_workbook(ws.contracts, Path(tmp) / "a.xlsx", refs,
                                             lang=ui.lang_of(request)).read_bytes()
        return download(data, f"{stem(ws)}-art30-assessments.xlsx", XLSX)

    @app.post("/w/{wid}/contracts/import")
    async def import_assessments(request: Request, wid: str,
                                 file: Annotated[UploadFile, File()]) -> Response:
        ws = ui.ws_or_404(wid)
        t = ui.t(request)
        got = await ui.read_upload(file, ASSESSMENT_SUFFIXES)
        if isinstance(got, str):
            msg = t("err.too_large") if got == "size" else t("err.upload_type",
                                                              suffix=got.split(":", 1)[1])
            raise HTTPException(status_code=400, detail=msg)
        name, data = got
        try:
            if name.lower().endswith(".json"):
                problems: list[str] = []
                book = AssessmentBook.from_json(data)
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "assessments.xlsx"
                    path.write_bytes(data)
                    book, problems = read_assessment_workbook(path)
        except (ValueError, ValidationError, KeyError, OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(status_code=400,
                                detail=t("err.read", name=name, error=str(exc)[:300])) from exc
        user = ui.user_of(request)
        with ws.lock:
            new, updated = ws.contracts.merge(book, source=name, by=user)
            ws.programme_changed("art30", name[:200], f"Imported {new} new and {updated} "
                                 "updated assessment(s)", user)
        return RedirectResponse(f"/w/{wid}/contracts?imported={new + updated}&updated={updated}"
                                f"&problems={len(problems)}", status_code=303)

    # ------------------------------------------------------------------ one contract

    def assessment_page(request: Request, ws: Workspace, ref: str,
                        draft: ContractAssessment | None = None,
                        suggestions: SuggestionResult | None = None,
                        document: Any = None, error: str | None = None,
                        status: int = 200) -> HTMLResponse:
        contexts = contract_contexts(ws.register)
        ctx = contexts.get(ref)
        stored = ws.contracts.get(ref)
        if ctx is None and stored is None:
            raise HTTPException(status_code=404)
        if ctx is None:  # assessment of an arrangement that is no longer in the register
            ctx = ContractContext(ref, in_register=False)
        current = draft or stored or ContractAssessment(contract_ref=ref)
        preview_book = AssessmentBook(assessments=dict(ws.contracts.assessments))
        preview_book.assessments[ref] = current
        compliance = evaluate_contract(ctx, preview_book)
        callofs = sorted(r for r, c in contexts.items() if c.overarching_ref == ref)
        b0201 = next((c.row for c in ws.register.b_02_01 if c.contract_ref == ref), None)
        return ui.ws_page(
            request, ws, "ws_contract.html.j2", "programme", status=status, ctx=ctx,
            ref=ref, a=current, stored=stored, compliance=compliance,
            items={i.provision.id: i for i in compliance.items},
            provisions=applicable(ctx.critical), all_provisions=PROVISIONS,
            draft=draft is not None, suggestions=suggestions.by_id() if suggestions else {},
            suggestion_counts=suggestions.counts() if suggestions else None,
            document=document, callofs=callofs, b0201=b0201, statuses=list(ProvisionStatus),
            progress_options=list(RemediationProgress),
            pdf=pdf_supported(), sample_doc=ref == SAMPLE_CONTRACT_REF and ws.kind == "sample",
            action_url=contract_url(ws.id, ref), contract_url=contract_url, error=error,
            hints=consistency_hints(ws.register, compliance),
            provider_codes=set(ws.register.providers_by_code()))

    @app.get("/w/{wid}/contract/{ref:path}", response_class=HTMLResponse)
    def contract(request: Request, wid: str, ref: str) -> HTMLResponse:
        return assessment_page(request, ui.ws_or_404(wid), ref)

    @app.post("/w/{wid}/contract/{ref:path}")
    async def contract_save(request: Request, wid: str, ref: str,
                            file: Annotated[UploadFile | None, File()] = None,
                            action: Annotated[str, Form()] = "save") -> Response:
        ws = ui.ws_or_404(wid)
        t = ui.t(request)
        if ref not in contract_contexts(ws.register) and ws.contracts.get(ref) is None:
            raise HTTPException(status_code=404)
        user = ui.user_of(request)
        if action == "delete":
            with ws.lock:
                ws.contracts.remove(ref)
                ws.programme_changed("art30", ref, "Assessment deleted", user)
            return RedirectResponse(f"/w/{wid}/contracts", status_code=303)
        if action in ("suggest", "sample"):
            return await _suggest(request, ws, ref, file, action == "sample")
        form = await request.form()
        assessment = _from_form(ref, form)
        if assessment is None:
            return assessment_page(request, ws, ref, error=t("c30.ui.invalid"), status=400)
        if not assessment.assessor and user != DEFAULT_USER:
            assessment = assessment.model_copy(update={"assessor": user})
        with ws.lock:
            stored = ws.contracts.save(assessment, by=user)
            ws.programme_changed("art30", ref, stored.history[-1].summary, user)
        return RedirectResponse(contract_url(wid, ref) + "?saved=1", status_code=303)

    async def _suggest(request: Request, ws: Workspace, ref: str, file: UploadFile | None,
                       use_sample: bool) -> HTMLResponse:
        t = ui.t(request)
        if use_sample:
            name, data = SAMPLE_CONTRACT_NAME, docx_bytes(SAMPLE_CONTRACT_TEXT)
        else:
            if file is None or not file.filename:
                return assessment_page(request, ws, ref, error=t("c30.ui.no_file"), status=400)
            got = await ui.read_upload(file, DOC_SUFFIXES)
            if isinstance(got, str):
                msg = (t("err.too_large") if got == "size"
                       else t("c30.ui.doc_type", suffix=got.split(":", 1)[1]))
                return assessment_page(request, ws, ref, error=msg, status=400)
            name, data = got
        try:
            extracted = extract_text(name, data)
        except ExtractionError as exc:
            return assessment_page(request, ws, ref, status=400,
                                   error=t("c30.ui.extract_failed", name=name, error=str(exc)))
        ctx = contract_contexts(ws.register).get(ref)
        result = suggest(extracted.text, critical=ctx.critical if ctx else True)
        base = ws.contracts.get(ref) or ContractAssessment(contract_ref=ref)
        draft = apply_suggestions(base, result, lang=ui.lang_of(request))
        draft = draft.model_copy(update={"document": name[:300],
                                         "assessed_on": base.assessed_on or date.today()})
        return assessment_page(request, ws, ref, draft=draft, suggestions=result,
                               document=extracted)


def _from_form(ref: str, form: Any) -> ContractAssessment | None:
    try:
        assessed_on = (date.fromisoformat(form_text(form, "assessed_on"))
                       if form_text(form, "assessed_on") else None)
        a = ContractAssessment(
            contract_ref=ref, assessor=form_text(form, "assessor", 200),
            assessed_on=assessed_on, document=form_text(form, "document", 300),
            notes=form_text(form, "notes"),
            inherit=form_text(form, "inherit") == "1" if form_text(form, "inherit_shown")
            else True)
        for p in PROVISIONS:
            raw = form_text(form, f"st-{p.id}")
            if not raw and not form_text(form, f"ev-{p.id}") and not form_text(form, f"cl-{p.id}"):
                continue
            sug = form_text(form, f"sg-{p.id}")
            status = ProvisionStatus.parse(raw)
            reason = form_text(form, f"exr-{p.id}", 1000)
            until_raw = form_text(form, f"exu-{p.id}")
            until = date.fromisoformat(until_raw) if until_raw else None
            if reason and (until is None or status not in (ProvisionStatus.MISSING,
                                                           ProvisionStatus.PARTIAL)):
                raise ValueError("an exception needs a gap and an end date")
            remediation = None
            if status in (ProvisionStatus.MISSING, ProvisionStatus.PARTIAL):
                due_raw = form_text(form, f"rd-{p.id}")
                remediation = (RemediationProgress.parse(form_text(form, f"rp-{p.id}")),
                               form_text(form, f"ro-{p.id}", 200),
                               date.fromisoformat(due_raw) if due_raw else None)
            a.set(p.id, status, form_text(form, f"cl-{p.id}", 200),
                  form_text(form, f"ev-{p.id}"),
                  suggested=ProvisionStatus.parse(sug) if sug else None,
                  exception=(reason, form_text(form, f"exa-{p.id}", 200), until)
                  if reason else None, remediation=remediation)
    except (ValueError, ValidationError):
        return None
    return a


__all__ = ["ComplianceStatus", "contract_url", "register"]
