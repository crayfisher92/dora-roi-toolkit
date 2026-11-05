"""Workbench screens for ICT-related incidents: log, guided classification, reporting clock.

* ``/w/{id}/incidents`` – log with status, classification and next deadline, recurring
  incidents, exports (summary HTML/JSON, log JSON) and import;
* ``/w/{id}/incidents/new`` and ``/w/{id}/incidents/{incident}`` – the guided questionnaire
  (criteria of the RTS on classification), the result with the criteria and thresholds that
  triggered, the reporting deadlines as a countdown, report submissions and status changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import ValidationError

from dora_roi.incidents.classify import classify
from dora_roi.incidents.criteria import DEFAULT_THRESHOLDS, Criterion, criteria
from dora_roi.incidents.deadlines import humanise
from dora_roi.incidents.model import (
    TIMEZONES,
    Answers,
    Incident,
    IncidentLog,
    IncidentStatus,
    ReportKind,
    RootCause,
)
from dora_roi.incidents.report import (
    incident_view,
    overview,
    render_summary_html,
    summary_dict,
)
from dora_roi.model.refdata import EEA_COUNTRIES, country_name
from dora_roi.web.context import Ui, download, form_text, stem
from dora_roi.workspace import Workspace

BOOL_FIELDS = ("critical_services", "malicious_access", "relevant_clients", "media",
               "complaints", "regulatory_breach", "client_loss", "data_impact")
INT_FIELDS = ("clients_affected", "clients_total", "counterparts_affected",
              "counterparts_total", "transactions_affected", "transactions_daily")
DEC_FIELDS = ("transaction_value_affected", "transaction_value_daily", "economic_eur")
FLOAT_FIELDS = ("duration_hours", "downtime_hours")
TIME_FIELDS = ("occurred_at", "detected_at", "classified_at", "resolved_at")
SECTIONS: tuple[tuple[Criterion, tuple[str, ...]], ...] = (
    (Criterion.CRITICAL_SERVICES, ("critical_services", "malicious_access")),
    (Criterion.CLIENTS, ("clients_affected", "clients_total", "counterparts_affected",
                         "counterparts_total", "transactions_affected", "transactions_daily",
                         "transaction_value_affected", "transaction_value_daily",
                         "relevant_clients")),
    (Criterion.REPUTATION, ("media", "complaints", "regulatory_breach", "client_loss")),
    (Criterion.DURATION, ("duration_hours", "downtime_hours")),
    (Criterion.GEOGRAPHY, ("member_states",)),
    (Criterion.DATA, ("data_impact",)),
    (Criterion.ECONOMIC, ("economic_eur",)),
)


class FormError(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


def _now() -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0)


def _parse_time(raw: str, log: IncidentLog, field: str) -> datetime | None:
    if not raw:
        return None
    try:
        local = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise FormError(field) from exc
    if local.tzinfo is None:
        local = local.replace(tzinfo=log.tz)
    return local.astimezone(UTC)


def _number(raw: str, kind: type, field: str) -> Any:
    if not raw:
        return None
    text = raw.replace(" ", "").replace(" ", "").replace("'", "")
    if kind is not float and "," in text and "." not in text:
        text = text.replace(",", "")
    text = text.replace(",", ".")
    try:
        value = kind(text) if kind is not Decimal else Decimal(text)
    except (ValueError, InvalidOperation) as exc:
        raise FormError(field) from exc
    if value < 0:
        raise FormError(field)
    return value


def incident_from_form(form: Any, log: IncidentLog, incident_id: str,
                       old: Incident | None) -> Incident:
    """Build an incident from the questionnaire; raises :class:`FormError` on bad input."""
    answers: dict[str, Any] = {}
    for name in BOOL_FIELDS:
        raw = form_text(form, f"a-{name}")
        answers[name] = {"yes": True, "no": False}.get(raw)
    for name in INT_FIELDS:
        answers[name] = _number(form_text(form, f"a-{name}"), int, name)
    for name in DEC_FIELDS:
        answers[name] = _number(form_text(form, f"a-{name}"), Decimal, name)
    for name in FLOAT_FIELDS:
        answers[name] = _number(form_text(form, f"a-{name}"), float, name)
    states = [s for s in form.getlist("ms") if isinstance(s, str) and s in EEA_COUNTRIES] \
        if hasattr(form, "getlist") else []
    answers["member_states"] = states or None
    times = {name: _parse_time(form_text(form, name), log, name) for name in TIME_FIELDS}
    if times["detected_at"] is None:
        raise FormError("detected_at")
    title = form_text(form, "title", 200)
    if not title:
        raise FormError("title")
    status = form_text(form, "status") or IncidentStatus.OPEN.value
    cause = form_text(form, "root_cause")

    def many(name: str) -> list[str]:
        values = form.getlist(name) if hasattr(form, "getlist") else []
        return [v.strip()[:200] for v in values if isinstance(v, str) and v.strip()]

    try:
        return Incident(
            id=incident_id, title=title, description=form_text(form, "description"),
            status=IncidentStatus(status), owner=form_text(form, "owner", 200),
            occurred_at=times["occurred_at"], detected_at=times["detected_at"],
            classified_at=times["classified_at"], resolved_at=times["resolved_at"],
            entity_leis=many("entity"), provider_codes=many("provider"),
            contract_refs=many("contract"),
            root_cause=RootCause(cause) if cause else None,
            recurrence_key=form_text(form, "recurrence_key", 120),
            authority_reference=form_text(form, "authority_reference", 120),
            answers=Answers(**answers),
            initial_submitted_at=old.initial_submitted_at if old else None,
            intermediate_submitted_at=old.intermediate_submitted_at if old else None,
            final_submitted_at=old.final_submitted_at if old else None,
            history=old.history if old else [])
    except (ValidationError, ValueError) as exc:
        raise FormError("form") from exc


def register(app: FastAPI, ui: Ui) -> None:
    def local(ws: Workspace) -> Any:
        tz = ws.incidents.tz

        def fmt(moment: datetime | None, form: bool = False) -> str:
            if moment is None:
                return "" if form else "—"
            value = moment.astimezone(tz)
            return value.strftime("%Y-%m-%dT%H:%M") if form else value.strftime(
                "%Y-%m-%d %H:%M")

        return fmt

    def page_ctx(request: Request, ws: Workspace) -> dict[str, Any]:
        lang = ui.lang_of(request)
        return {"local": local(ws), "tzname": ws.incidents.timezone, "now": _now(),
                "humanise": lambda d: humanise(d, lang),
                "criteria": {c.key: c for c in criteria()}}

    @app.get("/w/{wid}/incidents", response_class=HTMLResponse)
    def incidents(request: Request, wid: str, imported: int = -1) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        ov = overview(ws.incidents, ws.register, _now())
        return ui.ws_page(request, ws, "ws_incidents.html.j2", "programme", ov=ov,
                          imported=imported, timezones=TIMEZONES, **page_ctx(request, ws))

    @app.post("/w/{wid}/incidents/settings")
    async def settings(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        tz = form_text(await request.form(), "timezone")
        if tz in TIMEZONES:
            ws.incidents.timezone = tz
        return RedirectResponse(f"/w/{wid}/incidents", status_code=303)

    @app.get("/w/{wid}/incidents/summary.html", response_class=HTMLResponse)
    def summary_html(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        ov = overview(ws.incidents, ws.register, _now())
        return HTMLResponse(render_summary_html(ov, lang=ui.lang_of(request),
                                                client=ws.report.maintainer_name or ws.name,
                                                timezone=ws.incidents.timezone))

    @app.get("/w/{wid}/incidents/summary.json")
    def summary_json(wid: str) -> JSONResponse:
        ws = ui.ws_or_404(wid)
        ov = overview(ws.incidents, ws.register, _now())
        return JSONResponse(summary_dict(ov, ws.incidents.timezone))

    @app.get("/w/{wid}/incidents/log.json")
    def log_json(wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        return download(ws.incidents.to_json().encode(), f"{stem(ws)}-incident-log.json",
                        "application/json")

    @app.post("/w/{wid}/incidents/import")
    async def import_log(request: Request, wid: str,
                         file: Annotated[UploadFile, File()]) -> Response:
        ws = ui.ws_or_404(wid)
        t = ui.t(request)
        got = await ui.read_upload(file, {".json"})
        if isinstance(got, str):
            msg = t("err.too_large") if got == "size" else t("err.upload_type",
                                                              suffix=got.split(":", 1)[1])
            raise HTTPException(status_code=400, detail=msg)
        name, data = got
        try:
            other = IncidentLog.from_json(data)
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400,
                                detail=t("err.read", name=name, error=str(exc)[:300])) from exc
        n = ws.incidents.merge(other)
        return RedirectResponse(f"/w/{wid}/incidents?imported={n}", status_code=303)

    # ------------------------------------------------------------------ one incident

    def form_page(request: Request, ws: Workspace, incident: Incident, new: bool,
                  error_field: str | None = None, status: int = 200) -> HTMLResponse:
        now = _now()
        view = incident_view(incident, ws.register, now)
        reg = ws.register
        providers = sorted(((p.provider_code, p.legal_name or p.provider_code)
                            for p in reg.b_05_01 if p.provider_code),
                           key=lambda x: x[1].casefold())
        contracts = sorted({c.contract_ref for c in reg.b_02_01 if c.contract_ref})
        t = ui.t(request)
        error = None
        if error_field:
            label = (t("inc.ui.f." + error_field) if error_field in (*TIME_FIELDS, "title", "form")
                     else t("inc.q." + error_field))
            error = t("inc.ui.form_error", field=label)
        return ui.ws_page(
            request, ws, "ws_incident.html.j2", "programme", status=status, inc=incident,
            view=view, new=new, sections=SECTIONS, bool_fields=BOOL_FIELDS,
            providers=providers, contracts=contracts,
            entities=[(e.lei, e.name or e.lei) for e in reg.b_01_02 if e.lei],
            states=sorted(EEA_COUNTRIES), country_name=country_name,
            statuses=list(IncidentStatus), causes=list(RootCause), report_kinds=list(ReportKind),
            error=error, error_field=error_field,
            action_url=f"/w/{ws.id}/incidents/{'new' if new else incident.id}",
            thresholds=DEFAULT_THRESHOLDS, **page_ctx(request, ws))

    @app.get("/w/{wid}/incidents/new", response_class=HTMLResponse)
    def new_incident(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        now = _now()
        draft = Incident(id=ws.incidents.next_id(now), title="-", detected_at=now)
        return form_page(request, ws, draft.model_copy(update={"title": ""}), True)

    @app.post("/w/{wid}/incidents/new")
    async def create_incident(request: Request, wid: str) -> Response:
        ws = ui.ws_or_404(wid)
        form = await request.form()
        new_id = ws.incidents.next_id(_now())
        try:
            incident = incident_from_form(form, ws.incidents, new_id, None)
        except FormError as exc:
            draft = Incident(id=new_id, title=form_text(form, "title", 200) or "-",
                             detected_at=_now())
            return form_page(request, ws, draft, True, exc.field, 400)
        _save(ws, incident, None, form_text(form, "by", 200))
        return RedirectResponse(f"/w/{wid}/incidents/{new_id}?saved=1", status_code=303)

    @app.get("/w/{wid}/incidents/{iid}", response_class=HTMLResponse)
    def incident_page(request: Request, wid: str, iid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        incident = ws.incidents.get(iid)
        if incident is None:
            raise HTTPException(status_code=404)
        return form_page(request, ws, incident, False)

    @app.post("/w/{wid}/incidents/{iid}")
    async def incident_action(request: Request, wid: str, iid: str) -> Response:
        ws = ui.ws_or_404(wid)
        old = ws.incidents.get(iid)
        if old is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        action = form_text(form, "action") or "save"
        by = form_text(form, "by", 200)
        target = f"/w/{wid}/incidents/{iid}"
        if action == "delete":
            ws.incidents.remove(iid)
            return RedirectResponse(f"/w/{wid}/incidents", status_code=303)
        if action == "report":
            kind = form_text(form, "kind")
            if kind not in {k.value for k in ReportKind}:
                raise HTTPException(status_code=400)
            try:
                when = _parse_time(form_text(form, "submitted_at"), ws.incidents,
                                   "submitted_at") or _now()
            except FormError as exc:
                raise HTTPException(status_code=400, detail="submitted_at") from exc
            ws.incidents.save(old.model_copy(update={f"{kind}_submitted_at": when}),
                              f"report_{kind}", by=by,
                              note=form_text(form, "authority_reference", 120))
            return RedirectResponse(target + "?saved=1", status_code=303)
        if action in ("resolve", "close", "reopen"):
            update: dict[str, Any] = {"status": {"resolve": IncidentStatus.RESOLVED,
                                                 "close": IncidentStatus.CLOSED,
                                                 "reopen": IncidentStatus.OPEN}[action]}
            if action == "resolve" and old.resolved_at is None:
                update["resolved_at"] = _now()
            ws.incidents.save(old.model_copy(update=update),
                              {"resolve": "resolved", "close": "closed",
                               "reopen": "reopened"}[action], by=by)
            return RedirectResponse(target + "?saved=1", status_code=303)
        try:
            incident = incident_from_form(form, ws.incidents, iid, old)
        except FormError as exc:
            return form_page(request, ws, old, False, exc.field, 400)
        _save(ws, incident, old, by)
        return RedirectResponse(target + "?saved=1", status_code=303)


def _save(ws: Workspace, incident: Incident, old: Incident | None, by: str) -> None:
    """Save and record classification changes; timestamp the first major classification."""
    now = _now()
    before = classify(old, now).outcome if old else None
    result = classify(incident, now)
    if result.major and incident.classified_at is None:
        incident = incident.model_copy(update={"classified_at": now})
    stored = ws.incidents.save(incident, "created" if old is None else "updated", by=by,
                               at=now)
    if result.outcome is not before:
        ws.incidents.save(stored, "classified", by=by, at=now,
                          note=f"{before.value if before else '—'} → {result.outcome.value}")
