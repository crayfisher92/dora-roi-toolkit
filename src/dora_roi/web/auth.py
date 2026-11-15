"""Sign-in through a single-sign-on reverse proxy (``docs/TEAM_DEPLOYMENT.md``).

The workbench has no login of its own. For team use it runs behind an authenticating reverse
proxy – the reference set-up is oauth2-proxy with Microsoft Entra ID – that signs the user in
and forwards the identity in a request header (``X-Forwarded-Email`` by default). The header is
trusted **only** on connections from the configured proxy addresses; every other request is
refused, so a client that reaches the app directly cannot claim an identity.

Without an identity header configured the app runs in local single-user mode: browser
sessions are the isolation boundary and the audit-trail name is self-declared.

Configuration (environment or ``roi serve`` options):

* ``ROI_AUTH_HEADER`` – header carrying the signed-in user, e.g. ``X-Forwarded-Email``;
* ``ROI_TRUSTED_PROXIES`` – comma-separated IP addresses or networks of the proxy
  (default ``127.0.0.1,::1``).
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp

from dora_roi.web.security import CURRENT_SESSION

DEFAULT_TRUSTED_PROXIES = "127.0.0.1,::1"
#: Reachable without an identity: container health probes and static assets.
OPEN_PATHS = ("/api/health", "/static/")
MAX_IDENTITY_LENGTH = 254  # longest valid e-mail address

Network = IPv4Network | IPv6Network

#: Signed-in user of the current request (``""`` in local single-user mode).
CURRENT_USER: ContextVar[str] = ContextVar("roi_signed_in_user", default="")


def parse_networks(value: str) -> tuple[Network, ...]:
    """``"10.0.0.5, 172.28.0.0/24"`` → networks; raises ``ValueError`` for invalid entries."""
    return tuple(ip_network(part.strip(), strict=False) for part in value.split(",")
                 if part.strip())


@dataclass(frozen=True)
class AuthConfig:
    """Where the signed-in user comes from (``header=None``: local single-user mode)."""

    header: str | None = None
    trusted_proxies: tuple[Network, ...] = field(
        default_factory=lambda: parse_networks(DEFAULT_TRUSTED_PROXIES))

    @property
    def enabled(self) -> bool:
        return bool(self.header)

    @classmethod
    def from_env(cls) -> AuthConfig:
        header = os.environ.get("ROI_AUTH_HEADER", "").strip() or None
        proxies = os.environ.get("ROI_TRUSTED_PROXIES", "").strip() or DEFAULT_TRUSTED_PROXIES
        return cls(header, parse_networks(proxies))

    def is_trusted(self, host: str | None) -> bool:
        try:
            address = ip_address(host or "")
        except ValueError:
            return False
        return any(address in network for network in self.trusted_proxies)


def clean_identity(value: str) -> str:
    """Printable, trimmed, case-folded identity (e-mail addresses compare case-insensitively)."""
    text = "".join(ch for ch in value if ch.isprintable()).strip().lower()
    return text if len(text) <= MAX_IDENTITY_LENGTH else ""


def current_owner() -> str:
    """Key that owns workspaces: the signed-in user, else the browser session."""
    user = CURRENT_USER.get()
    return f"user:{user}" if user else CURRENT_SESSION.get()


class IdentityMiddleware(BaseHTTPMiddleware):
    """Take the signed-in user from the proxy's header; refuse requests without one."""

    def __init__(self, app: ASGIApp, config: AuthConfig) -> None:
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        config = self.config
        if not config.enabled or request.url.path.startswith(OPEN_PATHS):
            return await call_next(request)
        if not config.is_trusted(request.client.host if request.client else None):
            return PlainTextResponse("Use the sign-in address of the workbench.",
                                     status_code=403)
        identity = clean_identity(request.headers.get(config.header or "", ""))
        if not identity:
            return PlainTextResponse("Not signed in.", status_code=401)
        token = CURRENT_USER.set(identity)
        try:
            return await call_next(request)
        finally:
            CURRENT_USER.reset(token)
