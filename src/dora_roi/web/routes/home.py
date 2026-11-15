"""Home page, imports, samples, project files and the audit-trail name."""

from __future__ import annotations

import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from dora_roi import __version__
from dora_roi.inventory import (
    InventoryError,
)
from dora_roi.io.excel import write_blank_template
from dora_roi.io.loader import UnsupportedInputError, load_raw
from dora_roi.project import SUFFIX as PROJECT_SUFFIX
from dora_roi.project import ProjectError, load_project
from dora_roi.sample import generate_previous_year, generate_sample, register_to_raw
from dora_roi.sample.programme import load_sample_programme
from dora_roi.web.auth import CURRENT_USER, current_owner
from dora_roi.web.context import (
    ROI_SUFFIXES,
    Ctx,
)
from dora_roi.web.helpers import (
    XLSX,
    _download,
    _reason,
    clean_user,
)
from dora_roi.web.i18n import translator
from dora_roi.web.security import (
    cookie_secure,
    safe_next,
)
from dora_roi.web.spaces import (
    PRIVATE,
    file_stamp,
)
from dora_roi.workspace import Workspace

router = APIRouter()


@router.post("/project/open")
async def open_project(ctx: Ctx, request: Request, file: Annotated[UploadFile, File()]) -> Response:
    got = await ctx.read_upload(file, {PROJECT_SUFFIX})
    if isinstance(got, str):
        return ctx.upload_error(request, got, "home.html.j2", **ctx.home_ctx())
    name, data = got

    def load() -> Workspace:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"project{PROJECT_SUFFIX}"
            path.write_bytes(data)
            ws = load_project(path)
        ws.id = uuid.uuid4().hex  # never reuse an id from a file (session isolation)
        ctx.own(ws, request)
        return ws

    try:
        ws = await ctx.offload(load)
    except ProjectError as exc:
        t = translator(ctx.lang_of(request))
        return ctx.render(request, "home.html.j2", status=400,
                      error=t("err.read", name=name, error=str(exc)), **ctx.home_ctx())
    return RedirectResponse(f"/w/{ws.id}", status_code=303)

@router.post("/projects/open")
async def open_saved(ctx: Ctx, request: Request) -> Response:
    if not ctx.autosave:
        raise HTTPException(status_code=404)
    form = await request.form()
    space = str(form.get("space", PRIVATE))
    # only files listed in the user's ctx.own ctx.spaces (no paths)
    match = ctx.spaces.resolve(space, str(form.get("file", "")), CURRENT_USER.get())
    if match is None:
        raise HTTPException(status_code=404)
    me = current_owner()
    for open_ws in ctx.workspaces.values():  # already open for this user: go there
        if open_ws.session.owner == me and open_ws.session.read_only is None and \
                open_ws.session.project_path is not None and \
                open_ws.session.project_path.resolve() == match.resolve():
            return RedirectResponse(f"/w/{open_ws.id}", status_code=303)
    holder = ctx.locks.holder(match)

    def load() -> Workspace:
        ws = load_project(match)
        ws.id = uuid.uuid4().hex
        if holder is not None:  # someone else is editing: read-only view
            ws.session.read_only = holder.user
        else:
            ws.session.project_path = match
            ws.session.project_stamp = file_stamp(match)
        ctx.own(ws, request, space)
        return ws

    try:
        ws = await ctx.offload(load)
    except ProjectError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/w/{ws.id}", status_code=303)

@router.get("/", response_class=HTMLResponse)
def home(ctx: Ctx, request: Request) -> HTMLResponse:
    return ctx.render(request, "home.html.j2", **ctx.home_ctx())

@router.get("/api/health")
def health(ctx: Ctx) -> dict[str, str]:
    return {"status": "ok", "version": __version__}

@router.get("/template.xlsx")
def blank_template(ctx: Ctx) -> Response:
    with tempfile.TemporaryDirectory() as tmp:
        data = write_blank_template(Path(tmp) / "t.xlsx").read_bytes()
    return _download(data, "roi-template.xlsx", XLSX)

@router.post("/import")
async def import_roi(ctx: Ctx, request: Request, file: Annotated[UploadFile, File()]) -> Response:
    got = await ctx.read_upload(file, ROI_SUFFIXES)
    if isinstance(got, str):
        return ctx.upload_error(request, got, "home.html.j2", **ctx.home_ctx())
    name, data = got

    def build() -> Workspace:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"upload{Path(name).suffix.lower()}"
            path.write_bytes(data)
            raw, _ = load_raw(path)
        raw.source = name
        return ctx.own(Workspace(name, raw, source=name), request)

    try:
        ws = await ctx.offload(build)
    except (UnsupportedInputError, zipfile.BadZipFile, InventoryError, KeyError,
            ValueError, OSError) as exc:
        t = translator(ctx.lang_of(request))
        return ctx.render(request, "home.html.j2", status=400,
                      error=t("err.read", name=name, error=_reason(exc)), **ctx.home_ctx())
    return RedirectResponse(f"/w/{ws.id}", status_code=303)

@router.post("/sample")
def sample(ctx: Ctx, request: Request, variant: Annotated[str, Form()] = "dirty") -> Response:
    if variant == "pair":
        prev = generate_previous_year()
        cur = generate_sample(inject_errors=False)
        old_ws = Workspace("Alpenrand 2024", register_to_raw(prev.source_register),
                           kind="sample")
        new_ws = Workspace("Alpenrand 2025", register_to_raw(cur.source_register),
                           kind="sample")
        load_sample_programme(new_ws)
        ctx.own(old_ws, request)
        ctx.own(new_ws, request)
        return RedirectResponse(f"/w/{new_ws.id}/compare?other={old_ws.id}", status_code=303)
    clean = variant == "clean"
    result = generate_sample(inject_errors=not clean)
    name = "Alpenrand (clean)" if clean else "Alpenrand (25 injected errors)"
    ws = Workspace(name, register_to_raw(result.source_register), kind="sample")
    load_sample_programme(ws)
    return ctx.add_workspace(ws, request)

@router.post("/user")
async def set_user(ctx: Ctx, request: Request) -> Response:
    if ctx.auth.enabled:  # the sign-in proxy decides who the user is
        raise HTTPException(status_code=404)
    form = await request.form()
    name = clean_user(str(form.get("name", "")))
    target = safe_next(str(form.get("next", "")), "/")
    response = RedirectResponse(target, status_code=303)
    response.set_cookie("roi_user", name, max_age=31536000, samesite="strict",
                        httponly=True, secure=cookie_secure(request))
    return response
