"""HTTP security controls for the workbench (``docs/SECURITY.md``).

* :class:`SecurityHeadersMiddleware` – CSP, anti-framing, no-sniff, no referrer, isolation.
* :class:`SameOriginMiddleware` – rejects state-changing requests from other origins (CSRF).
* :class:`BodySizeLimitMiddleware` – refuses oversized request bodies before reading them.
* :func:`safe_next` – only same-site relative redirect targets.
"""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Workbench pages: no inline script, everything from our own origin.
APP_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
           "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
#: Self-contained HTML reports (inline script/style by design, no network access at all).
REPORT_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
              "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
REPORT_PATHS = re.compile(r"^/w/[0-9a-f]+/(download/(executive|validation)\.html|"
                          r"contracts/plan\.html|incidents/summary\.html|readiness\.html)$")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    # "same-origin", not "no-referrer": with no-referrer browsers send ``Origin: null`` on
    # same-origin form posts, which the CSRF check must reject
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in BASE_HEADERS.items():
            response.headers.setdefault(name, value)
        csp = REPORT_CSP if REPORT_PATHS.match(request.url.path) else APP_CSP
        response.headers.setdefault("Content-Security-Policy", csp)
        if request.url.path.startswith(("/w/", "/map/", "/api/")):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _origin_of(value: str | None) -> str | None:
    if not value:
        return None
    parts = urlsplit(value)
    return parts.netloc.lower() if parts.scheme and parts.netloc else "invalid"


class SameOriginMiddleware(BaseHTTPMiddleware):
    """Reject cross-site state-changing requests (Origin / Referer / Sec-Fetch-Site)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in UNSAFE_METHODS and not _same_origin(request):
            return PlainTextResponse("Cross-site request blocked", status_code=403)
        return await call_next(request)


def _same_origin(request: Request) -> bool:
    site = request.headers.get("sec-fetch-site")
    if site is not None:  # modern browsers: authoritative
        return site in ("same-origin", "none")
    host = (request.headers.get("host") or "").lower()
    origin = _origin_of(request.headers.get("origin")) or _origin_of(
        request.headers.get("referer"))
    return origin is None or origin == host


TOO_LARGE = b"Request too large."


class BodySizeLimitMiddleware:
    """Refuse request bodies above ``max_bytes`` before they are read (HTTP 413).

    A declared ``Content-Length`` above the limit is rejected at once, without reading the
    body. Bodies without one (chunked uploads) are counted while they stream in; once past the
    limit the application sees the end of the body, nothing more is read from the client, and
    whatever the application answers (typically a parse error) is replaced by a 413 that keeps
    its security headers. Pure ASGI, so nothing is buffered first.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.max_bytes:
            response = PlainTextResponse(TOO_LARGE.decode(), status_code=413,
                                         headers={"Connection": "close"})
            await response(scope, receive, send)
            return
        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def guarded_send(message: Message) -> None:
            if not exceeded:
                await send(message)
            elif message["type"] == "http.response.start":
                skip = {b"content-length", b"content-type", b"connection"}
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in skip]
                headers += [(b"content-type", b"text/plain; charset=utf-8"),
                            (b"content-length", str(len(TOO_LARGE)).encode()),
                            (b"connection", b"close")]
                await send({"type": "http.response.start", "status": 413, "headers": headers})
                await send({"type": "http.response.body", "body": TOO_LARGE})
            # the application's own body is dropped

        await self.app(scope, limited_receive, guarded_send)


_BAD_REDIRECT = re.compile(r"[\\\x00-\x1f]")


def safe_next(target: str | None, default: str) -> str:
    """Return ``target`` only if it is a same-site path (no scheme, host, ``//`` or ``\\``)."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return default
    if _BAD_REDIRECT.search(target) or urlsplit(target).netloc:
        return default
    return target


# --------------------------------------------------------------------------- sessions

SESSION_COOKIE = "roi_session"
_SESSION_RE = re.compile(r"^[A-Za-z0-9_\-]{43}$")
CURRENT_SESSION: ContextVar[str] = ContextVar("roi_session", default="")


class SessionMiddleware(BaseHTTPMiddleware):
    """Give every browser an unguessable session id (HttpOnly, SameSite=Strict cookie).

    Workspaces and wizards belong to the session that created them; other sessions get 404
    (``BACKLOG`` B-18). There are no accounts – the session *is* the isolation boundary.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        sid = request.cookies.get(SESSION_COOKIE, "")
        new = not _SESSION_RE.match(sid)
        if new:
            sid = secrets.token_urlsafe(32)
        token = CURRENT_SESSION.set(sid)
        try:
            response = await call_next(request)
        finally:
            CURRENT_SESSION.reset(token)
        if new:
            response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="strict",
                                secure=request.url.scheme == "https", path="/")
        return response
