"""HTTP security controls for the workbench (``docs/SECURITY.md``).

* :class:`SecurityHeadersMiddleware` – CSP, anti-framing, no-sniff, no referrer, isolation.
* :class:`SameOriginMiddleware` – rejects state-changing requests from other origins (CSRF).
* :func:`safe_next` – only same-site relative redirect targets.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

#: Workbench pages: no inline script, everything from our own origin.
APP_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
           "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
           "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
#: Self-contained HTML reports (inline script/style by design, no network access at all).
REPORT_CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
              "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
REPORT_PATHS = re.compile(r"^/w/[0-9a-f]+/download/(executive|validation)\.html$")
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


_BAD_REDIRECT = re.compile(r"[\\\x00-\x1f]")


def safe_next(target: str | None, default: str) -> str:
    """Return ``target`` only if it is a same-site path (no scheme, host, ``//`` or ``\\``)."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return default
    if _BAD_REDIRECT.search(target) or urlsplit(target).netloc:
        return default
    return target
