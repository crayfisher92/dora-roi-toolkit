"""DORA RoI Workbench – FastAPI web application.

Server-rendered pages (Jinja2) with progressive enhancement: every action is a plain HTML form
or link; ``static/app.js`` adds in-place cell saving, filtering, graph highlighting and the
theme switch. See ``docs/UX.md`` for the personas and screen flow.

Workspaces live **in memory only** (bounded LRU, with a per-user share) and are discarded when
the process stops unless a projects folder is configured; uploads are parsed from temporary
files that are deleted immediately. Parsing, validation and saving run in worker threads, so
one large upload does not block other users. Run locally (single user) or behind a sign-in
proxy for team use (``dora_roi.web.auth``, ``docs/TEAM_DEPLOYMENT.md``).
"""

from __future__ import annotations

import contextvars
import io
import math
import os
import re
import tempfile
import threading
import time
import uuid
import zipfile
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, Generic, TypeVar
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape
from starlette.concurrency import run_in_threadpool

from dora_roi import __version__
from dora_roi.audit import audit_csv, column_label
from dora_roi.diff import diff_registers
from dora_roi.explain import explain, rule_title
from dora_roi.fixes import bulk_groups, findings_by_template, suggest
from dora_roi.graph import build_graph, chains_table, render_svg
from dora_roi.inventory import (
    FIELDS,
    FIELDS_BY_KEY,
    EntityInfo,
    InventoryError,
    InventorySheet,
    build_raw,
    preview,
    read_inventory,
    suggest_mapping,
)
from dora_roi.io.csv_folder import register_to_csv_texts
from dora_roi.io.excel import write_blank_template, write_raw_workbook
from dora_roi.io.limits import InputTooLargeError
from dora_roi.io.loader import UnsupportedInputError, load_raw
from dora_roi.io.xbrl_csv import XbrlCsvOptions, build_package_files, package_name
from dora_roi.lei import is_valid_lei
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE, EntityType
from dora_roi.model.refdata import COUNTRIES, CURRENCIES, country_name
from dora_roi.project import SUFFIX as PROJECT_SUFFIX
from dora_roi.project import ProjectError, list_projects, load_project, save_project
from dora_roi.reporting import render_html, render_json, render_markdown
from dora_roi.reporting.executive import build_charts, money, pct, render_executive_summary
from dora_roi.reporting.pdf import PdfBusyError, html_to_pdf, pdf_available
from dora_roi.reporting.validation_report import render_xlsx
from dora_roi.sample import generate_previous_year, generate_sample, register_to_raw
from dora_roi.validation import RULES, Finding, finding_key
from dora_roi.web.auth import CURRENT_USER, AuthConfig, IdentityMiddleware, current_owner
from dora_roi.web.i18n import LANGUAGES, pick_language, translator
from dora_roi.web.security import (
    BodySizeLimitMiddleware,
    SameOriginMiddleware,
    SecurityHeadersMiddleware,
    SessionMiddleware,
    safe_next,
)
from dora_roi.web.spaces import (
    PRIVATE,
    TEAM,
    ProjectLocks,
    ProjectSpaces,
    conflict_path,
    file_stamp,
    unique_path,
)
from dora_roi.web.views import display, provider_profile, stepper
from dora_roi.workspace import DEFAULT_USER, Change, EditError, Workspace

#: download kinds → how they appear in the audit trail
EXPORT_LABELS = {
    "project": "Project file", "xlsx": "Excel workbook", "csv": "CSV files",
    "xbrl": "xBRL-CSV package", "validation.html": "Validation report (HTML)",
    "validation.md": "Validation report (Markdown)", "validation.json": "Validation report (JSON)",
    "validation.pdf": "Validation report (PDF)", "validation.xlsx": "Findings (Excel)",
    "executive.html": "Executive summary (HTML)",
    "executive.pdf": "Executive summary (PDF)", "analysis.json": "Concentration analysis (JSON)",
    "audit.csv": "Audit log (CSV)",
}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
#: Request bodies above this are refused before they are read (upload plus form overhead).
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
MAX_WORKSPACES = 20
#: Per signed-in user (or browser session): workspaces and rows held in memory.
MAX_USER_WORKSPACES = 10
MAX_USER_ROWS = 200_000
#: Imports, project loads and edits running at the same time (memory and CPU bound).
MAX_PARALLEL_JOBS = 4
PAGE_SIZE = 50
FIX_GROUP_LIMIT = 25
ROI_SUFFIXES = {".xlsx", ".xlsm", ".zip"}
INVENTORY_SUFFIXES = {".xlsx", ".xlsm", ".csv"}
STATIC_DIR = Path(__file__).parent / "static"
T = TypeVar("T")


class LRUStore(Generic[T]):
    """Thread-safe bounded store.

    Bounded by item count and, optionally, by a total ``weight`` (for workspaces: the number
    of rows, which drives memory – roughly 2 KB per row once parsed and validated). With an
    ``owner`` function each owner additionally gets its own count and weight budget, and an
    owner over budget loses its *own* least recently used items first – one user loading
    large registers cannot push everyone else's work out. The most recently added item is
    always kept; ``on_evict`` is called for every evicted item (outside the lock).
    """

    def __init__(self, capacity: int, *, max_weight: int | None = None,
                 weight: Callable[[T], int] | None = None,
                 owner: Callable[[T], str] | None = None, owner_capacity: int | None = None,
                 owner_weight: int | None = None,
                 on_evict: Callable[[T], None] | None = None) -> None:
        self.capacity = capacity
        self.max_weight = max_weight
        self.owner_capacity = owner_capacity
        self.owner_weight = owner_weight
        self._weight = weight
        self._owner = owner
        self._on_evict = on_evict
        self._items: OrderedDict[str, T] = OrderedDict()
        self._lock = Lock()

    def _total_weight(self, keys: list[str] | None = None) -> int:
        weigh = self._weight
        if weigh is None:
            return 0
        items = self._items.values() if keys is None else [self._items[k] for k in keys]
        return sum(weigh(v) for v in items)

    def _evict_own(self, key: str, item: T) -> list[T]:
        owner = self._owner
        if owner is None:
            return []
        mine = owner(item)
        evicted: list[T] = []
        while True:
            others = [k for k, v in self._items.items() if k != key and owner(v) == mine]
            over_count = self.owner_capacity is not None and len(others) >= self.owner_capacity
            over_weight = (self.owner_weight is not None and others
                           and self._total_weight([*others, key]) > self.owner_weight)
            if not others or not (over_count or over_weight):
                return evicted
            evicted.append(self._items.pop(others[0]))

    def add(self, key: str, item: T) -> None:
        with self._lock:
            self._items[key] = item
            self._items.move_to_end(key)
            evicted = self._evict_own(key, item)
            while len(self._items) > self.capacity:
                evicted.append(self._items.popitem(last=False)[1])
            if self.max_weight is not None:
                while len(self._items) > 1 and self._total_weight() > self.max_weight:
                    evicted.append(self._items.popitem(last=False)[1])
        if self._on_evict is not None:
            for gone in evicted:
                self._on_evict(gone)

    def remove(self, key: str) -> T | None:
        with self._lock:
            return self._items.pop(key, None)

    def peek(self, key: str) -> T | None:
        """The item without marking it as used (``None`` if absent)."""
        with self._lock:
            return self._items.get(key)

    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._items

    def get(self, key: str) -> T:
        with self._lock:
            if key not in self._items:
                raise HTTPException(status_code=404, detail="not found")
            self._items.move_to_end(key)
            return self._items[key]

    def values(self) -> list[T]:
        with self._lock:
            return list(reversed(self._items.values()))


@dataclass
class Wizard:
    id: str
    sheet: InventorySheet
    mapping: dict[int, str]
    entity: EntityInfo | None = None
    owner: str = ""


def _env() -> Environment:
    env = Environment(
        loader=ChoiceLoader([PackageLoader("dora_roi", "web/templates"),
                             PackageLoader("dora_roi", "reporting/templates")]),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(money=money, pct=pct, version=__version__, display=display,
                       country_name=country_name, templates=TEMPLATE_MODELS, RULES=RULES,
                       languages=LANGUAGES, finding_key=finding_key)
    return env


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def max_store_rows() -> int:
    """Row budget for all workspaces held in memory (``ROI_MAX_STORE_ROWS``)."""
    return _env_int("ROI_MAX_STORE_ROWS", 500_000)


def create_app(capacity: int | None = None, projects_dir: str | Path | None = None,
               auth: AuthConfig | None = None) -> FastAPI:
    """The workbench application.

    ``auth`` (default: from ``ROI_AUTH_HEADER`` / ``ROI_TRUSTED_PROXIES``) switches on team
    mode: users are identified by the sign-in proxy, own their workspaces across browsers and
    get a private and a team project space.
    """
    auth = auth if auth is not None else AuthConfig.from_env()
    capacity = capacity or _env_int("ROI_MAX_WORKSPACES", MAX_WORKSPACES)
    app = FastAPI(title="DORA RoI Workbench", version=__version__,
                  description="Prepare, fix and analyse a DORA register of information.")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(IdentityMiddleware, config=auth)
    app.add_middleware(SessionMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

    def release_lock(ws: Workspace) -> None:
        if ws.project_path is not None:
            locks.release(ws.project_path, ws.id)

    workspaces: LRUStore[Workspace] = LRUStore(
        capacity, max_weight=max_store_rows(), weight=Workspace.row_count,
        owner=lambda ws: ws.owner,
        owner_capacity=_env_int("ROI_MAX_USER_WORKSPACES", MAX_USER_WORKSPACES),
        owner_weight=_env_int("ROI_MAX_USER_ROWS", MAX_USER_ROWS), on_evict=release_lock)
    wizards: LRUStore[Wizard] = LRUStore(capacity)
    app.state.workspaces = workspaces
    app.state.wizards = wizards
    app.state.auth = auth
    env = _env()
    job_slots = threading.BoundedSemaphore(_env_int("ROI_MAX_PARALLEL_JOBS", MAX_PARALLEL_JOBS))

    async def offload(fn: Callable[[], T]) -> T:
        """Run blocking work (parsing, validation, saving) in a worker thread, at most
        ``ROI_MAX_PARALLEL_JOBS`` at a time, with the request's context (signed-in user)."""
        def limited() -> T:
            with job_slots:
                return fn()

        return await run_in_threadpool(contextvars.copy_context().run, limited)

    def lang_of(request: Request) -> str:
        return pick_language(request.query_params.get("lang"), request.cookies.get("lang"),
                             request.headers.get("accept-language"))

    def render(request: Request, page_template: str, status: int = 200, **ctx: Any
               ) -> HTMLResponse:
        lang = lang_of(request)
        t = translator(lang)
        def lang_href(code: str) -> str:
            params = [(k, v) for k, v in request.query_params.multi_items() if k != "lang"]
            return request.url.path + "?" + urlencode([*params, ("lang", code)])

        html = env.get_template(page_template).render(
            request=request, lang=lang, t=t, path=request.url.path, lang_href=lang_href,
            explain=lambda rid: explain(rid, lang), rule_title=lambda rid: rule_title(rid, lang),
            signed_in=CURRENT_USER.get(), **ctx)
        response = HTMLResponse(html, status_code=status)
        if request.query_params.get("lang") in LANGUAGES:
            response.set_cookie("lang", lang, max_age=31536000, samesite="lax")
        return response

    def ws_or_404(wid: str) -> Workspace:
        ws = workspaces.get(wid)
        if ws.owner != current_owner():
            raise HTTPException(status_code=404, detail="not found")
        ws.last_active = time.monotonic()
        return ws

    def ws_for_edit(wid: str) -> Workspace:
        """The workspace if this request may change it (it holds the project's edit lock)."""
        ws = ws_or_404(wid)
        if ws.read_only is None and ws.project_path is not None and \
                not locks.holds(ws.project_path, ws.id):
            holder = locks.acquire(ws.project_path, ws.id, ws.owner_label)
            if holder is not None:  # lock expired while idle and someone else took it
                ws.read_only = holder.user
                ws.on_change = None
                ws.notices.append(("ws.notice.lock_lost", {"user": holder.user}))
        if ws.read_only is not None:
            raise HTTPException(status_code=403,
                                detail=f"Read-only: {ws.read_only} is editing this project.")
        return ws

    def wiz_or_404(wid: str) -> Wizard:
        wiz = wizards.get(wid)
        if wiz.owner != current_owner():
            raise HTTPException(status_code=404, detail="not found")
        return wiz

    folder = Path(projects_dir or os.environ.get("ROI_PROJECTS_DIR", "") or ".")
    autosave = bool(projects_dir or os.environ.get("ROI_PROJECTS_DIR"))
    if autosave:
        folder.mkdir(parents=True, exist_ok=True)
    app.state.projects_dir = folder if autosave else None
    spaces = ProjectSpaces(folder, team_mode=auth.enabled)

    def last_active(wid: str) -> float:
        ws = workspaces.peek(wid)
        return ws.last_active if ws is not None else 0.0

    locks = ProjectLocks(alive=workspaces.contains, last_active=last_active)
    app.state.locks = locks

    def save_to_folder(ws: Workspace) -> None:
        """Autosave; never overwrite a file that changed on disk since it was read."""
        path = ws.project_path
        if ws.read_only is not None or path is None:
            return
        on_disk = file_stamp(path)
        if ws.project_stamp is not None and on_disk is not None and on_disk != ws.project_stamp:
            new = conflict_path(path)
            locks.release(path, ws.id)
            locks.acquire(new, ws.id, ws.owner_label)
            ws.project_path = path = new
            ws.notices.append(("ws.notice.conflict", {"file": new.name}))
        save_project(ws, path)
        ws.project_stamp = file_stamp(path)

    def own(ws: Workspace, request: Request, space: str = PRIVATE) -> Workspace:
        ws.owner = current_owner()
        ws.owner_label = user_of(request)
        ws.last_active = time.monotonic()
        if autosave and ws.read_only is None:
            target = spaces.folder(space, CURRENT_USER.get())
            if ws.project_path is None and target is not None:
                slug = re.sub(r"[^A-Za-z0-9]+", "-", Path(ws.name).stem).strip("-")[:40]
                ws.project_path = unique_path(target, f"{slug or 'register'}-{ws.id[:8]}")
            ws.space = space
            if ws.project_path is not None:
                holder = locks.acquire(ws.project_path, ws.id, ws.owner_label)
                if holder is not None:  # someone opened it a moment earlier
                    ws.read_only = holder.user
                else:
                    ws.on_change = save_to_folder
                    save_to_folder(ws)
        workspaces.add(ws.id, ws)
        return ws

    def my_workspaces() -> list[Workspace]:
        me = current_owner()
        return [w for w in workspaces.values() if w.owner == me]

    def ws_page(request: Request, ws: Workspace, page_template: str, step: str, **ctx: Any
                ) -> HTMLResponse:
        if step in ("analyse", "export"):
            ws.visited.add(step)
        return render(request, page_template, ws=ws, steps=stepper(ws, step), step=step,
                      user=user_of(request),
                      quality=ws.quality, counts=ws.report.severity_counts(), **ctx)

    def add_workspace(ws: Workspace, request: Request, space: str = PRIVATE
                      ) -> RedirectResponse:
        own(ws, request, space)
        return RedirectResponse(f"/w/{ws.id}", status_code=303)

    async def read_upload(file: UploadFile, allowed: set[str]) -> tuple[str, bytes] | str:
        name = Path(file.filename or "upload").name
        suffix = Path(name).suffix.lower()
        if suffix not in allowed:
            return f"type:{suffix or name}"
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            return "size"
        return name, data

    def upload_error(request: Request, code: str, page: str, **extra: Any) -> HTMLResponse:
        t = translator(lang_of(request))
        if code == "size":
            msg = t("err.too_large")
        else:
            msg = t("err.upload_type", suffix=code.split(":", 1)[1])
        return render(request, page, status=400, error=msg, **extra)

    # ------------------------------------------------------------------ home & basics

    def home_ctx() -> dict[str, Any]:
        project_spaces: list[tuple[str, list[tuple[Path, dict[str, str], str | None]]]] = []
        me = current_owner()
        for space in spaces.available() if autosave else ():
            target = spaces.folder(space, CURRENT_USER.get())
            items: list[tuple[Path, dict[str, str], str | None]] = []
            for path, meta in list_projects(target) if target is not None else []:
                holder = locks.holder(path)
                holder_ws = workspaces.peek(holder.workspace_id) if holder else None
                mine = holder_ws is not None and holder_ws.owner == me
                items.append((path, meta, holder.user if holder and not mine else None))
            project_spaces.append((space, items))
        return {"recent": my_workspaces(), "project_spaces": project_spaces if autosave else None,
                "team_mode": spaces.team_mode}

    @app.post("/project/open")
    async def open_project(request: Request, file: Annotated[UploadFile, File()]) -> Response:
        got = await read_upload(file, {PROJECT_SUFFIX})
        if isinstance(got, str):
            return upload_error(request, got, "home.html.j2", **home_ctx())
        name, data = got

        def load() -> Workspace:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"project{PROJECT_SUFFIX}"
                path.write_bytes(data)
                ws = load_project(path)
            ws.id = uuid.uuid4().hex  # never reuse an id from a file (session isolation)
            own(ws, request)
            return ws

        try:
            ws = await offload(load)
        except ProjectError as exc:
            t = translator(lang_of(request))
            return render(request, "home.html.j2", status=400,
                          error=t("err.read", name=name, error=str(exc)), **home_ctx())
        return RedirectResponse(f"/w/{ws.id}", status_code=303)

    @app.post("/projects/open")
    async def open_saved(request: Request) -> Response:
        if not autosave:
            raise HTTPException(status_code=404)
        form = await request.form()
        space = str(form.get("space", PRIVATE))
        # only files listed in the user's own spaces (no paths)
        match = spaces.resolve(space, str(form.get("file", "")), CURRENT_USER.get())
        if match is None:
            raise HTTPException(status_code=404)
        me = current_owner()
        for open_ws in workspaces.values():  # already open for this user: go there
            if open_ws.owner == me and open_ws.read_only is None and \
                    open_ws.project_path is not None and \
                    open_ws.project_path.resolve() == match.resolve():
                return RedirectResponse(f"/w/{open_ws.id}", status_code=303)
        holder = locks.holder(match)

        def load() -> Workspace:
            ws = load_project(match)
            ws.id = uuid.uuid4().hex
            if holder is not None:  # someone else is editing: read-only view
                ws.read_only = holder.user
            else:
                ws.project_path = match
                ws.project_stamp = file_stamp(match)
            own(ws, request, space)
            return ws

        try:
            ws = await offload(load)
        except ProjectError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/w/{ws.id}", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return render(request, "home.html.j2", **home_ctx())

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/template.xlsx")
    def blank_template() -> Response:
        with tempfile.TemporaryDirectory() as tmp:
            data = write_blank_template(Path(tmp) / "t.xlsx").read_bytes()
        return _download(data, "roi-template.xlsx", XLSX)

    @app.post("/import")
    async def import_roi(request: Request, file: Annotated[UploadFile, File()]) -> Response:
        got = await read_upload(file, ROI_SUFFIXES)
        if isinstance(got, str):
            return upload_error(request, got, "home.html.j2", **home_ctx())
        name, data = got

        def build() -> Workspace:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"upload{Path(name).suffix.lower()}"
                path.write_bytes(data)
                raw, _ = load_raw(path)
            raw.source = name
            return own(Workspace(name, raw, source=name), request)

        try:
            ws = await offload(build)
        except (UnsupportedInputError, zipfile.BadZipFile, InventoryError, KeyError,
                ValueError, OSError) as exc:
            t = translator(lang_of(request))
            return render(request, "home.html.j2", status=400,
                          error=t("err.read", name=name, error=_reason(exc)), **home_ctx())
        return RedirectResponse(f"/w/{ws.id}", status_code=303)

    @app.post("/sample")
    def sample(request: Request, variant: Annotated[str, Form()] = "dirty") -> Response:
        if variant == "pair":
            prev = generate_previous_year()
            cur = generate_sample(inject_errors=False)
            old_ws = Workspace("Alpenrand 2024", register_to_raw(prev.source_register),
                               kind="sample")
            new_ws = Workspace("Alpenrand 2025", register_to_raw(cur.source_register),
                               kind="sample")
            own(old_ws, request)
            own(new_ws, request)
            return RedirectResponse(f"/w/{new_ws.id}/compare?other={old_ws.id}", status_code=303)
        clean = variant == "clean"
        result = generate_sample(inject_errors=not clean)
        name = "Alpenrand (clean)" if clean else "Alpenrand (25 injected errors)"
        return add_workspace(Workspace(name, register_to_raw(result.source_register),
                                       kind="sample"), request)

    # ------------------------------------------------------------------ mapping wizard

    @app.get("/map", response_class=HTMLResponse)
    def wizard_start(request: Request) -> HTMLResponse:
        return render(request, "wizard_upload.html.j2", wstep=1)

    @app.post("/map")
    async def wizard_upload(request: Request, file: Annotated[UploadFile | None, File()] = None,
                            use_sample: Annotated[str | None, Form()] = None) -> Response:
        with tempfile.TemporaryDirectory() as tmp:
            if use_sample:
                from dora_roi.sample.inventory_sample import write_sample_inventory

                path = write_sample_inventory(Path(tmp) / "Vertragsinventar.xlsx")
                name = path.name
            else:
                if file is None or not file.filename:
                    return render(request, "wizard_upload.html.j2", status=400, wstep=1,
                                  error=translator(lang_of(request))("wiz.error.required"))
                got = await read_upload(file, INVENTORY_SUFFIXES)
                if isinstance(got, str):
                    return upload_error(request, got, "wizard_upload.html.j2", wstep=1)
                name, data = got
                # never use the client-supplied name as a path (T5 in docs/SECURITY.md)
                path = Path(tmp) / f"inventory{Path(name).suffix.lower()}"
                path.write_bytes(data)
            try:
                sheet = await offload(lambda: read_inventory(path))
            except Exception as exc:  # spreadsheet/csv readers raise many types on corrupt input
                t = translator(lang_of(request))
                return render(request, "wizard_upload.html.j2", status=400, wstep=1,
                              error=t("err.read", name=name, error=str(exc) or
                                      type(exc).__name__))
        sheet.source = name
        wiz = Wizard(uuid.uuid4().hex, sheet,
                     {s.column: s.field for s in suggest_mapping(sheet) if s.field})
        wiz.owner = current_owner()
        wizards.add(wiz.id, wiz)
        return RedirectResponse(f"/map/{wiz.id}", status_code=303)

    @app.get("/map/{wid}", response_class=HTMLResponse)
    def wizard_map(request: Request, wid: str) -> HTMLResponse:
        wiz = wiz_or_404(wid)
        suggestions = {s.column: s for s in suggest_mapping(wiz.sheet)}
        return render(request, "wizard_map.html.j2", wstep=2, wiz=wiz, fields=FIELDS,
                      suggestions=suggestions)

    @app.post("/map/{wid}")
    async def wizard_map_save(request: Request, wid: str) -> Response:
        wiz = wiz_or_404(wid)
        form = await request.form()
        mapping: dict[int, str] = {}
        for i in range(len(wiz.sheet.headers)):
            value = str(form.get(f"col{i}", "") or "")
            if value in FIELDS_BY_KEY and value not in mapping.values():
                mapping[i] = value
        wiz.mapping = mapping
        return RedirectResponse(f"/map/{wid}/entity", status_code=303)

    def entity_defaults(wiz: Wizard) -> EntityInfo:
        return wiz.entity or EntityInfo(lei="", name="", country="DE",
                                        reporting_date=date(date.today().year - 1, 12, 31))

    @app.get("/map/{wid}/entity", response_class=HTMLResponse)
    def wizard_entity(request: Request, wid: str) -> HTMLResponse:
        wiz = wiz_or_404(wid)
        return render(request, "wizard_entity.html.j2", wstep=3, wiz=wiz,
                      entity=entity_defaults(wiz), errors={}, entity_types=list(EntityType),
                      countries=COUNTRIES, currencies=sorted(CURRENCIES))

    @app.post("/map/{wid}/entity")
    async def wizard_entity_save(request: Request, wid: str) -> Response:
        wiz = wiz_or_404(wid)
        form = await request.form()
        t = translator(lang_of(request))

        def field(name: str) -> str:
            return str(form.get(name, "") or "").strip()

        errors: dict[str, str] = {}
        lei = field("lei").upper()
        if not is_valid_lei(lei):
            errors["lei"] = t("wiz.error.lei")
        for name in ("name", "country"):
            if not field(name):
                errors[name] = t("wiz.error.required")
        try:
            ref = date.fromisoformat(field("reporting_date"))
        except ValueError:
            errors["reporting_date"] = t("wiz.error.required")
            ref = date(date.today().year - 1, 12, 31)
        entity = EntityInfo(lei=lei, name=field("name"), country=field("country").upper(),
                            entity_type=field("entity_type") or EntityType.CREDIT_INSTITUTION,
                            competent_authority=field("competent_authority"),
                            reporting_date=ref, currency=field("currency").upper() or "EUR")
        wiz.entity = entity
        if errors:
            return render(request, "wizard_entity.html.j2", status=400, wstep=3, wiz=wiz,
                          entity=entity, errors=errors, entity_types=list(EntityType),
                          countries=COUNTRIES, currencies=sorted(CURRENCIES))
        return RedirectResponse(f"/map/{wid}/preview", status_code=303)

    @app.get("/map/{wid}/preview", response_class=HTMLResponse)
    def wizard_preview(request: Request, wid: str) -> Response:
        wiz = wiz_or_404(wid)
        if wiz.entity is None:
            return RedirectResponse(f"/map/{wid}/entity", status_code=303)
        rows = preview(wiz.sheet, wiz.mapping, limit=8)
        keys = [k for k in (f.key for f in FIELDS) if k in wiz.mapping.values()]
        return render(request, "wizard_preview.html.j2", wstep=4, wiz=wiz, rows=rows, keys=keys,
                      fields=FIELDS_BY_KEY)

    @app.post("/map/{wid}/import")
    def wizard_import(request: Request, wid: str) -> Response:
        wiz = wiz_or_404(wid)
        if wiz.entity is None:
            return RedirectResponse(f"/map/{wid}/entity", status_code=303)
        raw, notes = build_raw(wiz.sheet, wiz.mapping, wiz.entity)
        ws = Workspace(wiz.sheet.source or "inventory", raw, kind="inventory")
        ws.import_notes = notes.summary()
        return add_workspace(ws, request)

    # ------------------------------------------------------------------ workspace

    @app.get("/w/{wid}", response_class=HTMLResponse)
    def overview(request: Request, wid: str) -> HTMLResponse:
        ws = ws_or_404(wid)
        can_share = (autosave and spaces.team_mode and ws.space == PRIVATE
                     and ws.project_path is not None and ws.read_only is None)
        return ws_page(request, ws, "ws_overview.html.j2", "import",
                       notes=ws.import_notes, can_share=can_share)

    @app.get("/w/{wid}/fix", response_class=HTMLResponse)
    def fix(request: Request, wid: str, template: str | None = None,
            severity: str | None = None, rule: str | None = None) -> HTMLResponse:
        ws = ws_or_404(wid)
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
        return ws_page(request, ws, "ws_fix.html.j2", "fix", grouped=grouped,
                       template=template, by_sev=by_sev, severity=severity, rule=rule,
                       bulks=bulks, suggest=suggest, limit=FIX_GROUP_LIMIT,
                       column_label=_column_label, raw_value=lambda f: _raw_value(ws, f))

    @app.post("/w/{wid}/cell")
    async def edit_cell(request: Request, wid: str) -> Response:
        ws = ws_for_edit(wid)
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
            change = await offload(lambda: apply(row))
        except (ValueError, EditError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(_state_json(ws, template, row, column, change is not None,
                                            translator(lang_of(request))))
        target = safe_next(str(form.get("next", "")), f"/w/{wid}/fix")
        return RedirectResponse(target, status_code=303)

    @app.post("/w/{wid}/bulk")
    async def bulk(request: Request, wid: str) -> Response:
        ws = ws_for_edit(wid)
        form = await request.form()
        rows = [int(x) for x in str(form.get("rows", "")).split(",") if x.strip().isdigit()]
        user = user_of(request)

        def apply() -> None:
            ws.bulk_replace(str(form.get("template", "")), str(form.get("column", "")),
                            str(form.get("old", "")), str(form.get("new", "")), rows or None,
                            user=user)
            ws.report  # noqa: B018 - re-validate in the worker thread

        try:
            await offload(apply)
        except EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(safe_next(str(form.get("next", "")), f"/w/{wid}/fix"),
                                status_code=303)

    @app.get("/w/{wid}/register", response_class=HTMLResponse)
    def register_root(wid: str) -> Response:
        return RedirectResponse(f"/w/{wid}/register/B_01.01", status_code=303)

    @app.get("/w/{wid}/register/{template}", response_class=HTMLResponse)
    def register_table(request: Request, wid: str, template: str, q: str = "",
                       issues: int = 0, page: int = 1) -> HTMLResponse:
        ws = ws_or_404(wid)
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
        return ws_page(request, ws, "ws_register.html.j2", "fix", template=template, model=model,
                       rows=shown, total=len(rows), flagged=flagged, q=q, issues=issues,
                       page=page, pages=pages, table_counts=counts,
                       provider_link=_provider_link(ws))

    @app.get("/w/{wid}/register/{template}/{row}", response_class=HTMLResponse)
    def register_row(request: Request, wid: str, template: str, row: int) -> HTMLResponse:
        ws = ws_or_404(wid)
        try:
            raw_row = ws.row(template, row)
        except EditError as exc:
            raise HTTPException(status_code=404) from exc
        findings = ws.findings_for(template, row)
        return ws_page(request, ws, "ws_row.html.j2", "fix", template=template,
                       model=TEMPLATES_BY_CODE[template], raw_row=raw_row, findings=findings,
                       by_column={f.column: f for f in findings if f.column}, suggest=suggest)

    @app.post("/w/{wid}/register/{template}/{row}")
    async def register_row_save(request: Request, wid: str, template: str, row: int
                                ) -> Response:
        ws = ws_for_edit(wid)
        form = await request.form()
        user = user_of(request)
        if form.get("delete"):
            try:
                await offload(lambda: ws.delete_row(template, row, user=user))
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
            await offload(apply)
        except (EditError, KeyError) as exc:
            raise HTTPException(status_code=404) from exc
        return RedirectResponse(f"/w/{wid}/register/{template}/{row}?saved=1", status_code=303)

    @app.post("/w/{wid}/register/{template}")
    def register_add(request: Request, wid: str, template: str) -> Response:
        ws = ws_for_edit(wid)
        try:
            row = ws.add_row(template, user=user_of(request))
        except EditError as exc:
            raise HTTPException(status_code=404) from exc
        return RedirectResponse(f"/w/{wid}/register/{template}/{row}", status_code=303)

    @app.get("/w/{wid}/provider/{code}", response_class=HTMLResponse)
    def provider(request: Request, wid: str, code: str) -> HTMLResponse:
        ws = ws_or_404(wid)
        t = translator(lang_of(request))
        if code not in ws.register.providers_by_code() and not any(
                p.code == code for p in ws.analysis.providers):
            raise HTTPException(status_code=404)
        profile = provider_profile(ws, code, t)
        graph = build_graph(ws.register, focus=code)
        svg = render_svg(graph, link_prefix=f"/w/{wid}/provider/",
                         labels=_graph_labels(t)) if graph.edges else None
        return ws_page(request, ws, "ws_provider.html.j2", "analyse", p=profile, graph_svg=svg,
                       chains=chains_table(ws.register, code))

    @app.get("/w/{wid}/analyse", response_class=HTMLResponse)
    def analyse_page(request: Request, wid: str, color: str = "criticality",
                     critical: int = 0, isolated: int = 0) -> HTMLResponse:
        ws = ws_or_404(wid)
        t = translator(lang_of(request))
        color = color if color in ("criticality", "region") else "criticality"
        graph = build_graph(ws.register, critical_only=bool(critical),
                            with_isolated=bool(isolated))
        svg = render_svg(graph, color_by=color, link_prefix=f"/w/{wid}/provider/",
                         labels=_graph_labels(t))
        return ws_page(request, ws, "ws_analyse.html.j2", "analyse", a=ws.analysis,
                       charts=build_charts(ws.analysis), graph_svg=svg, color=color,
                       critical=critical, isolated=isolated, chains=chains_table(ws.register))

    @app.get("/w/{wid}/renewals", response_class=HTMLResponse)
    def renewals(request: Request, wid: str, critical: int = 0) -> HTMLResponse:
        from dora_roi.analytics.renewals import notice_schedule

        ws = ws_or_404(wid)
        items = notice_schedule(ws.register)
        if critical:
            items = [i for i in items if i.critical]
        return ws_page(request, ws, "ws_renewals.html.j2", "analyse", items=items,
                       critical=critical)

    @app.get("/w/{wid}/export", response_class=HTMLResponse)
    def export_page(request: Request, wid: str) -> HTMLResponse:
        return ws_page(request, ws_or_404(wid), "ws_export.html.j2", "export",
                       pdf=pdf_available())

    @app.get("/w/{wid}/download/{kind}")
    def download(request: Request, wid: str, kind: str) -> Response:
        ws = ws_or_404(wid)
        if kind not in EXPORT_LABELS:
            raise HTTPException(status_code=404)
        user = user_of(request)
        response = render_download(ws, kind, user, lang_of(request))
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
            pkg = package_name(ws.register, options)
            files, _ = build_package_files(ws.register, options)
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

    @app.get("/w/{wid}/compare", response_class=HTMLResponse)
    def compare(request: Request, wid: str, other: str | None = None,
                version: int | None = None, all: int = 0) -> HTMLResponse:
        ws = ws_or_404(wid)
        result = None
        label = None
        if other:
            o = ws_or_404(other)
            result = diff_registers(o.register, ws.register, o.name, ws.name)
            label = o.name
        elif version is not None:
            try:
                old = ws.register_at(version)
            except EditError as exc:
                raise HTTPException(status_code=404) from exc
            result = diff_registers(old, ws.register, f"v{version}", ws.name)
            label = f"v{version}"
        others = [w for w in my_workspaces() if w.id != ws.id]
        return ws_page(request, ws, "ws_compare.html.j2", "analyse", result=result, label=label,
                       others=others, other=other, version=version, show_all=bool(all))

    @app.post("/w/{wid}/compare")
    async def compare_upload(request: Request, wid: str,
                             file: Annotated[UploadFile, File()]) -> Response:
        ws = ws_or_404(wid)
        got = await read_upload(file, ROI_SUFFIXES)
        if isinstance(got, str):
            return upload_error(request, got, "ws_compare.html.j2", ws=ws,
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
            return own(Workspace(name, raw, source=name), request)

        try:
            other = await offload(build)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=type(exc).__name__) from exc
        return RedirectResponse(f"/w/{wid}/compare?other={other.id}", status_code=303)

    @app.post("/user")
    async def set_user(request: Request) -> Response:
        if auth.enabled:  # the sign-in proxy decides who the user is
            raise HTTPException(status_code=404)
        form = await request.form()
        name = clean_user(str(form.get("name", "")))
        target = safe_next(str(form.get("next", "")), "/")
        response = RedirectResponse(target, status_code=303)
        response.set_cookie("roi_user", name, max_age=31536000, samesite="strict",
                            httponly=True)
        return response

    @app.post("/w/{wid}/accept")
    async def accept(request: Request, wid: str) -> Response:
        ws = ws_for_edit(wid)
        form = await request.form()
        key = str(form.get("key", ""))
        finding = next((f for f in ws.report.findings if finding_key(f) == key), None)
        if finding is None:
            raise HTTPException(status_code=404)
        reason, user = str(form.get("reason", "")), user_of(request)
        try:
            await offload(lambda: ws.accept(finding, reason, user=user))
        except EditError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(safe_next(str(form.get("next", "")), f"/w/{wid}/fix"),
                                status_code=303)

    @app.post("/w/{wid}/unaccept")
    async def unaccept(request: Request, wid: str) -> Response:
        ws = ws_for_edit(wid)
        form = await request.form()
        key, user = str(form.get("key", "")), user_of(request)
        try:
            await offload(lambda: ws.unaccept(key, user=user))
        except EditError as exc:
            raise HTTPException(status_code=404) from exc
        return RedirectResponse(safe_next(str(form.get("next", "")), f"/w/{wid}/fix"),
                                status_code=303)

    @app.post("/w/{wid}/close")
    def close(wid: str) -> Response:
        """Release the edit lock and drop the workspace from memory (the file stays)."""
        ws = ws_or_404(wid)
        release_lock(ws)
        workspaces.remove(wid)
        return RedirectResponse("/", status_code=303)

    @app.post("/w/{wid}/share")
    def share(wid: str) -> Response:
        """Move a project from the user's private space to the team space."""
        ws = ws_for_edit(wid)
        old = ws.project_path
        team = spaces.folder(TEAM, "")
        if not (autosave and ws.space == PRIVATE and old is not None and team is not None):
            raise HTTPException(status_code=404)
        new = unique_path(team, old.stem)
        with ws.lock:
            save_project(ws, new)
            locks.release(old, ws.id)
            locks.acquire(new, ws.id, ws.owner_label)
            ws.project_path, ws.project_stamp, ws.space = new, file_stamp(new), TEAM
            old.unlink(missing_ok=True)
        ws.notices.append(("ws.notice.shared", {"file": new.name}))
        return RedirectResponse(f"/w/{wid}", status_code=303)

    @app.get("/w/{wid}/audit", response_class=HTMLResponse)
    def audit(request: Request, wid: str) -> HTMLResponse:
        ws = ws_or_404(wid)
        return ws_page(request, ws, "ws_audit.html.j2", "fix",
                       entries=list(reversed(ws.changes)), column_label=_column_label)

    @app.get("/w/{wid}/versions", response_class=HTMLResponse)
    def versions(request: Request, wid: str) -> HTMLResponse:
        ws = ws_or_404(wid)
        return ws_page(request, ws, "ws_versions.html.j2", "fix")

    @app.get("/api/w/{wid}")
    def api_summary(wid: str) -> JSONResponse:
        ws = ws_or_404(wid)
        q = ws.quality
        return JSONResponse({"id": ws.id, "name": ws.name, "score": q.score,
                             "readiness": q.readiness.value,
                             "counts": ws.report.severity_counts(),
                             "records": ws.report.record_counts})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if request.url.path.startswith("/api/") or \
                "application/json" in request.headers.get("accept", ""):
            response: Response = JSONResponse({"detail": exc.detail},
                                              status_code=exc.status_code)
        else:
            response = render(request, "error.html.j2", status=exc.status_code,
                              code=exc.status_code, detail=exc.detail)
        response.headers.update(exc.headers or {})  # e.g. Retry-After, Allow
        return response

    return app


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


app = create_app()

__all__ = ["app", "create_app"]
