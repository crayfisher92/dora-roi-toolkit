"""DORA RoI Workbench – FastAPI web application.

Server-rendered pages (Jinja2) with progressive enhancement: every action is a plain HTML form
or link; ``static/app.js`` adds in-place cell saving, filtering, graph highlighting and the
theme switch. See ``docs/UX.md`` for the personas and screen flow.

Workspaces live **in memory only** (bounded LRU, with a per-user share) and are discarded when
the process stops unless a projects folder is configured; uploads are parsed from temporary
files that are deleted immediately. Parsing, validation and saving run in worker threads, so
one large upload does not block other users. Run locally (single user) or behind a sign-in
proxy for team use (``dora_roi.web.auth``, ``docs/TEAM_DEPLOYMENT.md``).

Structure: :mod:`dora_roi.web.context` holds the shared state (stores, templates, project
spaces and locks, worker pool); the routes live in :mod:`dora_roi.web.routes` (``home``,
``wizard``, ``workspace``, ``analysis``, ``export``); this module wires them together.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from dora_roi import __version__
from dora_roi.web import contracts_routes, incidents_routes, programme_routes
from dora_roi.web.auth import AuthConfig, IdentityMiddleware
from dora_roi.web.context import (
    MAX_REQUEST_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_WORKSPACES,
    STATIC_DIR,
    WebContext,
    Wizard,
)
from dora_roi.web.feature_ui import Ui
from dora_roi.web.helpers import clean_user, user_of
from dora_roi.web.routes import analysis, export, home, wizard, workspace
from dora_roi.web.security import (
    BodySizeLimitMiddleware,
    SameOriginMiddleware,
    SecurityHeadersMiddleware,
    SessionMiddleware,
)
from dora_roi.web.store import LRUStore, max_store_rows

ROUTERS = (home.router, wizard.router, workspace.router, analysis.router, export.router)


def create_app(capacity: int | None = None, projects_dir: str | Path | None = None,
               auth: AuthConfig | None = None) -> FastAPI:
    """The workbench application.

    ``auth`` (default: from ``ROI_AUTH_HEADER`` / ``ROI_TRUSTED_PROXIES``) switches on team
    mode: users are identified by the sign-in proxy, own their workspaces across browsers and
    get a private and a team project space.
    """
    auth = auth if auth is not None else AuthConfig.from_env()
    # no interactive API docs: they publish the whole route surface and Swagger UI would load
    # scripts from a CDN (found by the security self-test, docs/SECURITY_TESTING.md)
    app = FastAPI(title="DORA RoI Workbench", version=__version__,
                  description="Prepare, fix and analyse a DORA register of information.",
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.add_middleware(SameOriginMiddleware)
    app.add_middleware(IdentityMiddleware, config=auth)
    app.add_middleware(SessionMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

    ctx = WebContext(capacity, projects_dir, auth)
    app.state.web = ctx
    app.state.workspaces = ctx.workspaces
    app.state.wizards = ctx.wizards
    app.state.auth = auth
    app.state.secure_cookies = auth.enabled or os.environ.get(
        "ROI_SECURE_COOKIES", "").strip().lower() in ("1", "true", "yes", "on")
    app.state.projects_dir = ctx.folder if ctx.autosave else None
    app.state.locks = ctx.locks
    for router in ROUTERS:
        app.include_router(router)
    # DORA programme modules: Art. 30 contracts, incidents, FINMA mapping, readiness
    ui = Ui(render=ctx.render, ws_page=ctx.ws_page, ws_or_404=ctx.ws_or_404,
            ws_for_edit=ctx.ws_for_edit, lang_of=ctx.lang_of, read_upload=ctx.read_upload,
            workspaces=ctx.my_workspaces, user_of=user_of)
    for module in (contracts_routes, incidents_routes, programme_routes):
        module.register(app, ui)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        if request.url.path.startswith("/api/") or \
                "application/json" in request.headers.get("accept", ""):
            response: Response = JSONResponse({"detail": exc.detail},
                                              status_code=exc.status_code)
        else:
            response = ctx.render(request, "error.html.j2", status=exc.status_code,
                                  code=exc.status_code, detail=exc.detail)
        response.headers.update(exc.headers or {})  # e.g. Retry-After, Allow
        return response

    return app


app = create_app()

__all__ = [
    "MAX_REQUEST_BYTES",
    "MAX_UPLOAD_BYTES",
    "MAX_WORKSPACES",
    "LRUStore",
    "WebContext",
    "Wizard",
    "app",
    "clean_user",
    "create_app",
    "max_store_rows",
    "user_of",
]
