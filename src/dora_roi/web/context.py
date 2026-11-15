"""Shared state of the workbench: stores, templates, project spaces, locks, worker pool."""

from __future__ import annotations

import contextvars
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypeVar
from urllib.parse import urlencode

from fastapi import Depends, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape
from starlette.concurrency import run_in_threadpool

from dora_roi import __version__
from dora_roi.explain import explain, rule_title
from dora_roi.inventory import (
    EntityInfo,
    InventorySheet,
)
from dora_roi.model import TEMPLATE_MODELS
from dora_roi.model.refdata import country_name
from dora_roi.project import list_projects, save_project
from dora_roi.reporting.executive import money, pct
from dora_roi.validation import RULES, finding_key
from dora_roi.web.auth import CURRENT_USER, AuthConfig, current_owner
from dora_roi.web.helpers import user_of
from dora_roi.web.i18n import LANGUAGES, pick_language, translator
from dora_roi.web.spaces import (
    PRIVATE,
    ProjectLocks,
    ProjectSpaces,
    conflict_path,
    file_stamp,
    unique_path,
)
from dora_roi.web.store import LRUStore, _env_int, max_store_rows
from dora_roi.web.views import display, stepper
from dora_roi.workspace import Workspace

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


class WebContext:
    """State and helpers shared by the routers: workspace and wizard stores, templates,
    project spaces and edit locks, and the worker-thread pool for blocking work."""

    def __init__(self, capacity: int | None, projects_dir: str | Path | None,
                 auth: AuthConfig) -> None:
        self.auth = auth
        capacity = capacity or _env_int("ROI_MAX_WORKSPACES", MAX_WORKSPACES)
        self.workspaces: LRUStore[Workspace] = LRUStore(
            capacity, max_weight=max_store_rows(), weight=Workspace.row_count,
            owner=lambda ws: ws.session.owner,
            owner_capacity=_env_int("ROI_MAX_USER_WORKSPACES", MAX_USER_WORKSPACES),
            owner_weight=_env_int("ROI_MAX_USER_ROWS", MAX_USER_ROWS),
            on_evict=self.release_lock)
        self.wizards: LRUStore[Wizard] = LRUStore(capacity)
        self.env = _env()
        self._job_slots = threading.BoundedSemaphore(
            _env_int("ROI_MAX_PARALLEL_JOBS", MAX_PARALLEL_JOBS))
        self.folder = Path(projects_dir or os.environ.get("ROI_PROJECTS_DIR", "") or ".")
        self.autosave = bool(projects_dir or os.environ.get("ROI_PROJECTS_DIR"))
        if self.autosave:
            self.folder.mkdir(parents=True, exist_ok=True)
        self.spaces = ProjectSpaces(self.folder, team_mode=auth.enabled)
        self.locks = ProjectLocks(alive=self.workspaces.contains, last_active=self.last_active)

    # ------------------------------------------------------------------ infrastructure

    def release_lock(self, ws: Workspace) -> None:
        if ws.session.project_path is not None:
            self.locks.release(ws.session.project_path, ws.id)

    def last_active(self, wid: str) -> float:
        ws = self.workspaces.peek(wid)
        return ws.session.last_active if ws is not None else 0.0

    async def offload(self, fn: Callable[[], T]) -> T:
        """Run blocking work (parsing, validation, saving) in a worker thread, at most
        ``ROI_MAX_PARALLEL_JOBS`` at a time, with the request's context (signed-in user)."""
        def limited() -> T:
            with self._job_slots:
                return fn()

        return await run_in_threadpool(contextvars.copy_context().run, limited)

    # ------------------------------------------------------------------ rendering

    def lang_of(self, request: Request) -> str:
        return pick_language(request.query_params.get("lang"), request.cookies.get("lang"),
                             request.headers.get("accept-language"))

    def render(self, request: Request, page_template: str, status: int = 200, **ctx: Any
               ) -> HTMLResponse:
        lang = self.lang_of(request)
        t = translator(lang)

        def lang_href(code: str) -> str:
            params = [(k, v) for k, v in request.query_params.multi_items() if k != "lang"]
            return request.url.path + "?" + urlencode([*params, ("lang", code)])

        html = self.env.get_template(page_template).render(
            request=request, lang=lang, t=t, path=request.url.path, lang_href=lang_href,
            explain=lambda rid: explain(rid, lang), rule_title=lambda rid: rule_title(rid, lang),
            signed_in=CURRENT_USER.get(), **ctx)
        response = HTMLResponse(html, status_code=status)
        if request.query_params.get("lang") in LANGUAGES:
            response.set_cookie("lang", lang, max_age=31536000, samesite="lax")
        return response

    def ws_page(self, request: Request, ws: Workspace, page_template: str, step: str,
                **ctx: Any) -> HTMLResponse:
        if step in ("analyse", "export"):
            ws.session.visited.add(step)
        return self.render(request, page_template, ws=ws, steps=stepper(ws, step), step=step,
                           user=user_of(request), quality=ws.quality,
                           counts=ws.report.severity_counts(), **ctx)

    def upload_error(self, request: Request, code: str, page: str, **extra: Any
                     ) -> HTMLResponse:
        t = translator(self.lang_of(request))
        if code == "size":
            msg = t("err.too_large")
        else:
            msg = t("err.upload_type", suffix=code.split(":", 1)[1])
        return self.render(request, page, status=400, error=msg, **extra)

    # ------------------------------------------------------------------ workspaces

    def ws_or_404(self, wid: str) -> Workspace:
        ws = self.workspaces.get(wid)
        if ws.session.owner != current_owner():
            raise HTTPException(status_code=404, detail="not found")
        ws.session.last_active = time.monotonic()
        return ws

    def ws_for_edit(self, wid: str) -> Workspace:
        """The workspace if this request may change it (it holds the project's edit lock)."""
        ws = self.ws_or_404(wid)
        if ws.session.read_only is None and ws.session.project_path is not None and \
                not self.locks.holds(ws.session.project_path, ws.id):
            holder = self.locks.acquire(ws.session.project_path, ws.id, ws.session.owner_label)
            if holder is not None:  # lock expired while idle and someone else took it
                ws.session.read_only = holder.user
                ws.on_change = None
                ws.session.notices.append(("ws.notice.lock_lost", {"user": holder.user}))
        if ws.session.read_only is not None:
            editor = ws.session.read_only
            raise HTTPException(status_code=403,
                                detail=f"Read-only: {editor} is editing this project.")
        return ws

    def wiz_or_404(self, wid: str) -> Wizard:
        wiz = self.wizards.get(wid)
        if wiz.owner != current_owner():
            raise HTTPException(status_code=404, detail="not found")
        return wiz

    def my_workspaces(self) -> list[Workspace]:
        me = current_owner()
        return [w for w in self.workspaces.values() if w.session.owner == me]

    def save_to_folder(self, ws: Workspace) -> None:
        """Autosave; never overwrite a file that changed on disk since it was read."""
        path = ws.session.project_path
        if ws.session.read_only is not None or path is None:
            return
        on_disk = file_stamp(path)
        known = ws.session.project_stamp
        if known is not None and on_disk is not None and on_disk != known:
            new = conflict_path(path)
            self.locks.release(path, ws.id)
            self.locks.acquire(new, ws.id, ws.session.owner_label)
            ws.session.project_path = path = new
            ws.session.notices.append(("ws.notice.conflict", {"file": new.name}))
        save_project(ws, path)
        ws.session.project_stamp = file_stamp(path)

    def own(self, ws: Workspace, request: Request, space: str = PRIVATE) -> Workspace:
        """Give ``ws`` to the current user, autosave it in ``space`` and keep it in memory."""
        ws.session.owner = current_owner()
        ws.session.owner_label = user_of(request)
        ws.session.last_active = time.monotonic()
        if self.autosave and ws.session.read_only is None:
            target = self.spaces.folder(space, CURRENT_USER.get())
            if ws.session.project_path is None and target is not None:
                slug = re.sub(r"[^A-Za-z0-9]+", "-", Path(ws.name).stem).strip("-")[:40]
                ws.session.project_path = unique_path(target, f"{slug or 'register'}-{ws.id[:8]}")
            ws.session.space = space
            if ws.session.project_path is not None:
                holder = self.locks.acquire(ws.session.project_path, ws.id, ws.session.owner_label)
                if holder is not None:  # someone opened it a moment earlier
                    ws.session.read_only = holder.user
                else:
                    ws.on_change = self.save_to_folder
                    self.save_to_folder(ws)
        self.workspaces.add(ws.id, ws)
        return ws

    def add_workspace(self, ws: Workspace, request: Request, space: str = PRIVATE
                      ) -> RedirectResponse:
        self.own(ws, request, space)
        return RedirectResponse(f"/w/{ws.id}", status_code=303)

    async def read_upload(self, file: UploadFile, allowed: set[str]
                          ) -> tuple[str, bytes] | str:
        name = Path(file.filename or "upload").name
        suffix = Path(name).suffix.lower()
        if suffix not in allowed:
            return f"type:{suffix or name}"
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            return "size"
        return name, data

    def home_ctx(self) -> dict[str, Any]:
        project_spaces: list[tuple[str, list[tuple[Path, dict[str, str], str | None]]]] = []
        me = current_owner()
        for space in self.spaces.available() if self.autosave else ():
            target = self.spaces.folder(space, CURRENT_USER.get())
            items: list[tuple[Path, dict[str, str], str | None]] = []
            for path, meta in list_projects(target) if target is not None else []:
                holder = self.locks.holder(path)
                holder_ws = self.workspaces.peek(holder.workspace_id) if holder else None
                mine = holder_ws is not None and holder_ws.session.owner == me
                items.append((path, meta, holder.user if holder and not mine else None))
            project_spaces.append((space, items))
        return {"recent": self.my_workspaces(),
                "project_spaces": project_spaces if self.autosave else None,
                "team_mode": self.spaces.team_mode}


def get_ctx(request: Request) -> WebContext:
    ctx: WebContext = request.app.state.web
    return ctx


#: Router dependency: ``def handler(ctx: Ctx, ...)``.
Ctx = Annotated[WebContext, Depends(get_ctx)]
