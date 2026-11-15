"""Helpers handed to the DORA programme route modules (Art. 30, incidents, FINMA, readiness).

``contracts_routes``, ``incidents_routes`` and ``programme_routes`` register their routes with
``register(app, ui)``; :func:`dora_roi.web.app.create_app` builds :class:`Ui` from the shared
:class:`~dora_roi.web.context.WebContext`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from dora_roi.web.i18n import translator
from dora_roi.workspace import Workspace

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Ui:
    render: Callable[..., HTMLResponse]
    ws_page: Callable[..., HTMLResponse]
    ws_or_404: Callable[[str], Workspace]
    #: The workspace if this request may change it (holds the project's edit lock, Phase 3).
    ws_for_edit: Callable[[str], Workspace]
    lang_of: Callable[[Request], str]
    read_upload: Callable[[UploadFile, set[str]], Awaitable[tuple[str, bytes] | str]]
    workspaces: Callable[[], list[Workspace]]
    #: Name entered for the audit trail (cookie), ``"local user"`` by default.
    user_of: Callable[[Request], str]

    def t(self, request: Request) -> Callable[..., str]:
        return translator(self.lang_of(request))

    def audit_export(self, request: Request, ws: Workspace, what: str) -> None:
        """Log a programme report or data export in the audit trail (as the base's exports,
        B-30): who produced what, from which state of the register."""
        ws.record_export(what, user=self.user_of(request))


def download(data: bytes, filename: str, media_type: str) -> Response:
    """Attachment response with a safe ASCII file name."""
    safe = "".join(c if (c.isascii() and c.isalnum()) or c in "-_." else "_"
                   for c in filename) or "download"
    return Response(data, media_type=media_type,
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def form_text(form: Any, name: str, limit: int = 4000) -> str:
    """A form field as stripped text, bounded in length."""
    value = form.get(name, "")
    return (value if isinstance(value, str) else "").strip()[:limit]


def stem(ws: Workspace) -> str:
    return Path(ws.name).stem.replace(" ", "_") or "register"
