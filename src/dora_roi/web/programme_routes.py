"""Workbench screens that combine the programme modules: the FINMA mapping (Swiss angle)
and – registered from here as well – the DORA readiness dashboard and report."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from dora_roi.finma import OPRISK, OUTSOURCING, evaluate_finma
from dora_roi.model.refdata import country_name
from dora_roi.web.context import Ui

CIRCULARS = ((OUTSOURCING, "FINMA Circular 2018/3 – Outsourcing"),
             (OPRISK, "FINMA Circular 2023/1 – Operational risks and resilience (banks)"))


def register(app: FastAPI, ui: Ui) -> None:
    @app.get("/w/{wid}/finma", response_class=HTMLResponse)
    def finma(request: Request, wid: str) -> HTMLResponse:
        ws = ui.ws_or_404(wid)
        view = evaluate_finma(ws.register, ws.portfolio, ws.incidents)
        return ui.ws_page(request, ws, "ws_finma.html.j2", "programme", view=view,
                          circulars=CIRCULARS, country_name=country_name)
