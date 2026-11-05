"""Small FastAPI front end: upload a register, see validation results and the dashboard.

Run with ``roi serve`` (or ``uvicorn dora_roi.web.app:create_app --factory``).

Analyses are kept **in memory only** for the lifetime of the process (bounded LRU); nothing
is written to disk except a temporary copy of the upload while it is parsed. The app is
meant for local or single-team use – put it behind authentication before exposing it.
"""

from __future__ import annotations

import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape

from dora_roi import __version__
from dora_roi.analytics import ConcentrationAnalysis, analyse
from dora_roi.api import validate_loaded
from dora_roi.io.excel import write_blank_template
from dora_roi.io.loader import LoadResult, UnsupportedInputError, load
from dora_roi.io.xbrl_csv import XbrlCsvOptions, build_package_files, package_name
from dora_roi.model import RegisterOfInformation
from dora_roi.reporting import render_html, render_json, render_markdown
from dora_roi.reporting.charts import TOOLTIP_SCRIPT
from dora_roi.reporting.executive import build_charts, money, pct, render_executive_summary
from dora_roi.validation import ValidationReport

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_SESSIONS = 20
ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".zip"}


@dataclass
class Analysis:
    id: str
    name: str
    register: RegisterOfInformation
    report: ValidationReport
    concentration: ConcentrationAnalysis
    created: datetime = field(default_factory=lambda: datetime.now(UTC))


class Store:
    """Bounded in-memory LRU store of analyses."""

    def __init__(self, capacity: int = MAX_SESSIONS) -> None:
        self.capacity = capacity
        self._items: OrderedDict[str, Analysis] = OrderedDict()
        self._lock = Lock()

    def add(self, item: Analysis) -> None:
        with self._lock:
            self._items[item.id] = item
            self._items.move_to_end(item.id)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def get(self, key: str) -> Analysis:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                raise HTTPException(status_code=404, detail="Analysis not found or expired")
            self._items.move_to_end(key)
            return item

    def recent(self) -> list[Analysis]:
        with self._lock:
            return list(reversed(self._items.values()))


def _env() -> Environment:
    env = Environment(
        loader=ChoiceLoader([PackageLoader("dora_roi", "web/templates"),
                             PackageLoader("dora_roi", "reporting/templates")]),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(money=money, pct=pct, version=__version__)
    return env


def _analyse(name: str, loaded: LoadResult) -> Analysis:
    report = validate_loaded(loaded)
    return Analysis(id=uuid.uuid4().hex[:12], name=name, register=loaded.register,
                    report=report, concentration=analyse(loaded.register))


def create_app(store: Store | None = None) -> FastAPI:
    """Application factory."""
    app = FastAPI(title="DORA RoI Toolkit", version=__version__,
                  description="Validate a DORA register of information and explore ICT "
                  "concentration risk.")
    app.state.store = store or Store()
    env = _env()

    def page(template: str, **ctx: Any) -> HTMLResponse:
        return HTMLResponse(env.get_template(template).render(**ctx))

    def get(analysis_id: str) -> Analysis:
        result: Analysis = app.state.store.get(analysis_id)
        return result

    @app.get("/", response_class=HTMLResponse)
    def index(error: str | None = None) -> HTMLResponse:
        return page("index.html.j2", recent=app.state.store.recent(), error=error)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/template.xlsx")
    def template() -> Response:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_blank_template(Path(tmp) / "roi-template.xlsx")
            data = path.read_bytes()
        return Response(data, media_type="application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet",
                        headers={"Content-Disposition": 'attachment; filename="roi-template.xlsx"'})

    @app.post("/upload")
    async def upload(file: Annotated[UploadFile, File()]) -> Response:
        name = Path(file.filename or "upload.xlsx").name
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            return index(error=f"Unsupported file type '{suffix or name}'. Upload an .xlsx "
                         "workbook or a .zip of CSV files / an xBRL-CSV package.")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            return index(error="File too large (limit 25 MB).")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"upload{suffix}"
            path.write_bytes(data)
            try:
                loaded = load(path)
            except (UnsupportedInputError, ValueError, KeyError, OSError) as exc:
                return index(error=f"Could not read '{name}': {exc}")
            except Exception as exc:  # openpyxl raises various errors on corrupt files
                return index(error=f"Could not read '{name}': {type(exc).__name__}")
        loaded.source = name
        item = _analyse(name, loaded)
        app.state.store.add(item)
        return RedirectResponse(f"/r/{item.id}", status_code=303)

    @app.post("/sample")
    def sample(clean: Annotated[bool, Form()] = False) -> Response:
        from dora_roi.sample import generate_sample

        result = generate_sample(inject_errors=not clean)
        name = "Alpenrand sample (clean)" if clean else "Alpenrand sample (with injected errors)"
        loaded = LoadResult(result.register, result.findings, name)
        item = _analyse(name, loaded)
        app.state.store.add(item)
        return RedirectResponse(f"/r/{item.id}", status_code=303)

    @app.get("/r/{analysis_id}", response_class=HTMLResponse)
    def result(analysis_id: str) -> HTMLResponse:
        item = get(analysis_id)
        return page("result.html.j2", item=item, report=item.report, a=item.concentration,
                    findings=item.report.sorted_findings()[:2000],
                    charts=build_charts(item.concentration), tooltip_script=TOOLTIP_SCRIPT)

    @app.get("/r/{analysis_id}/validation.json")
    def validation_json(analysis_id: str) -> Response:
        return Response(render_json(get(analysis_id).report), media_type="application/json")

    @app.get("/r/{analysis_id}/validation.md")
    def validation_md(analysis_id: str) -> Response:
        return Response(render_markdown(get(analysis_id).report), media_type="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="validation.md"'})

    @app.get("/r/{analysis_id}/validation.html", response_class=HTMLResponse)
    def validation_html(analysis_id: str) -> HTMLResponse:
        return HTMLResponse(render_html(get(analysis_id).report))

    @app.get("/r/{analysis_id}/executive.html", response_class=HTMLResponse)
    def executive(analysis_id: str) -> HTMLResponse:
        item = get(analysis_id)
        return HTMLResponse(render_executive_summary(item.register, item.report,
                                                     analysis=item.concentration))

    @app.get("/r/{analysis_id}/analysis.json")
    def analysis_json(analysis_id: str) -> JSONResponse:
        return JSONResponse(get(analysis_id).concentration.model_dump(mode="json"))

    @app.get("/r/{analysis_id}/xbrl-csv.zip")
    def xbrl(analysis_id: str) -> Response:
        import io
        import zipfile

        item = get(analysis_id)
        options = XbrlCsvOptions()
        name = package_name(item.register, options)
        files, _ = build_package_files(item.register, options)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, text in files.items():
                zf.writestr(f"{name}/{rel}", text)
        return Response(buf.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})

    return app


app = create_app()
