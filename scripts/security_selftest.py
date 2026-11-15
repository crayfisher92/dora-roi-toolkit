#!/usr/bin/env python3
"""Black-box security self-test of a running workbench (standard library only).

Run it against a local container in CI, or against the pilot deployment before go-live::

    python scripts/security_selftest.py http://127.0.0.1:8000
    python scripts/security_selftest.py https://roi.example.com --team --no-write \\
        --report security-selftest.md

``--team``      the URL is the public address of a team deployment behind the SSO proxy:
                requests without a sign-in (and with a forged identity header) must not reach
                the workbench.
``--no-write``  skip checks that create data (a sample workspace); use on shared instances.

Exit status 1 if any check fails. It complements, and does not replace, the tests in
``tests/test_security.py``, ``tests/test_hardening.py`` and ``tests/test_team.py`` and an
external penetration test (``docs/SECURITY_TESTING.md``).
"""

from __future__ import annotations

import argparse
import http.client
import sys
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"
IDENTITY_HEADERS = ("X-Forwarded-Email", "X-Forwarded-User", "X-Auth-Request-Email")


@dataclass
class Response:
    status: int
    headers: dict[str, list[str]]
    body: bytes

    def header(self, name: str) -> str:
        return ", ".join(self.headers.get(name.lower(), []))


@dataclass
class Result:
    check: str
    outcome: str
    detail: str = ""


@dataclass
class Target:
    base: str
    timeout: float = 15.0
    cookies: dict[str, str] = field(default_factory=dict)

    @property
    def parts(self) -> urllib.parse.SplitResult:
        return urllib.parse.urlsplit(self.base)

    @property
    def origin(self) -> str:
        return f"{self.parts.scheme}://{self.parts.netloc}"

    def request(self, method: str, path: str, *, headers: dict[str, str] | None = None,
                body: bytes | None = None, send_body: bool = True) -> Response:
        p = self.parts
        conn_cls = (http.client.HTTPSConnection if p.scheme == "https"
                    else http.client.HTTPConnection)
        conn = conn_cls(p.netloc, timeout=self.timeout)
        prefix = p.path.rstrip("/")
        hdrs = {"User-Agent": "dora-roi-security-selftest", "Accept": "text/html,*/*"}
        if self.cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        hdrs.update(headers or {})
        try:
            if send_body:
                conn.request(method, prefix + path, body=body, headers=hdrs)
            else:  # announce a body but never send it (size-limit check)
                conn.putrequest(method, prefix + path, skip_accept_encoding=True)
                for k, v in hdrs.items():
                    conn.putheader(k, v)
                conn.endheaders()
            raw = conn.getresponse()
            out: dict[str, list[str]] = {}
            for k, v in raw.getheaders():
                out.setdefault(k.lower(), []).append(v)
            data = raw.read(2_000_000)
        finally:
            conn.close()
        for cookie in out.get("set-cookie", []):
            name, _, rest = cookie.partition("=")
            self.cookies[name.strip()] = rest.split(";", 1)[0]
        return Response(raw.status, out, data)


Check = Callable[[Target], list[Result]]
REDIRECTS = (301, 302, 303, 307, 308)


def blocked(r: Response) -> bool:
    """Refused, or sent to the sign-in (team mode) – but not a successful POST redirect."""
    if r.status in (400, 401, 403, 404, 405, 413):
        return True
    return r.status in REDIRECTS and "/w/" not in r.header("location")


def check_headers(t: Target) -> list[Result]:
    r = t.request("GET", "/")
    if r.status != 200:
        return [Result("security headers", SKIP, f"GET / answered {r.status}")]
    out = []
    csp = r.header("content-security-policy")
    out.append(Result("Content-Security-Policy", PASS if "script-src 'self'" in csp
                      and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
                      else FAIL, csp or "missing"))
    expected = {"x-frame-options": "DENY", "x-content-type-options": "nosniff",
                "referrer-policy": "same-origin"}
    for name, value in expected.items():
        got = r.header(name)
        out.append(Result(name, PASS if got.lower() == value.lower() else FAIL, got or "missing"))
    leaks = [f"{h}: {r.header(h)}" for h in ("server", "x-powered-by") if r.header(h)]
    out.append(Result("no server/framework banner", FAIL if leaks else PASS, "; ".join(leaks)))
    if b"<script>" in r.body:
        out.append(Result("no inline script", FAIL, "inline <script> on the start page"))
    else:
        out.append(Result("no inline script", PASS))
    return out


def check_transport(t: Target) -> list[Result]:
    host = t.parts.hostname or ""
    if t.parts.scheme != "https":
        local = host in ("127.0.0.1", "localhost", "::1")
        return [Result("TLS", WARN if local else FAIL,
                       "plain HTTP on localhost" if local else "served without TLS")]
    r = t.request("GET", "/api/health")
    hsts = r.header("strict-transport-security")
    out = [Result("HSTS", PASS if "max-age=" in hsts else WARN,
                  hsts or "missing – set it on the ingress / load balancer")]
    plain = Target("http://" + t.parts.netloc, t.timeout)
    try:
        p = plain.request("GET", "/")
        ok = p.status in (301, 302, 307, 308) and p.header("location").startswith("https://")
        out.append(Result("HTTP redirects to HTTPS", PASS if ok else FAIL,
                          f"{p.status} {p.header('location')}"))
    except OSError:
        out.append(Result("HTTP redirects to HTTPS", PASS, "port 80 closed"))
    return out


def check_surface(t: Target) -> list[Result]:
    out = []
    for path in ("/docs", "/redoc", "/openapi.json"):
        r = t.request("GET", path)
        out.append(Result(f"no API docs at {path}", PASS if blocked(r) else FAIL, str(r.status)))
    r = t.request("TRACE", "/")
    out.append(Result("TRACE disabled", PASS if blocked(r) or r.status >= 400 else FAIL,
                      str(r.status)))
    for path in ("/static/../pyproject.toml", "/static/%2e%2e/%2e%2e/etc/passwd",
                 "/static/..%2f..%2fweb%2fapp.py"):
        r = t.request("GET", path)
        bad = r.status == 200 and (b"[project]" in r.body or b"root:" in r.body
                                   or b"def create_app" in r.body)
        out.append(Result(f"no path traversal ({path})", FAIL if bad else PASS, str(r.status)))
    r = t.request("GET", "/w/does-not-exist-0000")
    leak = any(s in r.body for s in (b"Traceback", b'File "', b"site-packages"))
    out.append(Result("errors without stack traces", FAIL if leak else PASS, str(r.status)))
    return out


def check_csrf(t: Target) -> list[Result]:
    out = []
    for name, hdrs in (("Origin", {"Origin": "https://evil.example"}),
                       ("Referer", {"Referer": "https://evil.example/x"}),
                       ("Sec-Fetch-Site", {"Sec-Fetch-Site": "cross-site"})):
        r = t.request("POST", "/sample", body=b"variant=clean", headers={
            "Content-Type": "application/x-www-form-urlencoded", **hdrs})
        out.append(Result(f"cross-site POST rejected ({name})", PASS if blocked(r) else FAIL,
                          str(r.status)))
    return out


def check_body_limit(t: Target) -> list[Result]:
    try:
        r = t.request("POST", "/import", headers={
            "Origin": t.origin, "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(10 * 1024**3)}, send_body=False)
    except OSError as exc:
        return [Result("oversized upload refused", PASS, f"connection closed ({exc})")]
    return [Result("oversized upload refused", PASS if blocked(r) else FAIL,
                   f"{r.status} for a 10 GiB announcement")]


def check_workspace(t: Target) -> list[Result]:
    r = t.request("POST", "/sample", body=b"variant=clean", headers={
        "Origin": t.origin, "Content-Type": "application/x-www-form-urlencoded"})
    loc = r.header("location")
    if r.status != 303 or "/w/" not in loc:
        return [Result("workspace created", SKIP, f"{r.status}")]
    wid = loc.rsplit("/w/", 1)[1].split("/")[0]
    out = [Result("workspace id unguessable", PASS if len(wid) >= 22 else FAIL,
                  f"{len(wid)} characters")]
    stranger = Target(t.base, t.timeout)  # no cookies: another browser
    s = stranger.request("GET", f"/w/{wid}")
    out.append(Result("workspace link useless in another browser",
                      FAIL if s.status == 200 else PASS, str(s.status)))
    page = t.request("GET", f"/w/{wid}/fix").body
    out.append(Result("online LEI check off unless enabled",
                      WARN if b"data-gleif" in page else PASS,
                      "ROI_GLEIF=1 is set" if b"data-gleif" in page else "off"))
    payload = urllib.parse.quote('"><svg onload=alert(1)>')
    x = t.request("GET", f"/w/{wid}/fix?template={payload}")
    out.append(Result("reflected input escaped", FAIL if b"<svg onload" in x.body else PASS))
    return out


def check_team(t: Target) -> list[Result]:
    out = []
    anon = Target(t.base, t.timeout).request("GET", "/")
    out.append(Result("anonymous request does not reach the workbench",
                      PASS if blocked(anon) else FAIL,
                      f"{anon.status} {anon.header('location')}"))
    for h in IDENTITY_HEADERS:
        forged = Target(t.base, t.timeout).request("GET", "/", headers={h: "mallory@evil.example"})
        out.append(Result(f"forged {h} ignored", PASS if blocked(forged) else FAIL,
                          str(forged.status)))
    start = Target(t.base, t.timeout).request("GET", "/oauth2/start?rd=%2F")
    cookies = start.headers.get("set-cookie", [])
    if cookies:
        weak = [c.split("=", 1)[0] for c in cookies
                if not all(flag in c.lower() for flag in ("secure", "httponly", "samesite"))]
        out.append(Result("sign-in cookies Secure, HttpOnly, SameSite",
                          FAIL if weak else PASS, ", ".join(weak)))
    else:
        out.append(Result("sign-in cookies Secure, HttpOnly, SameSite", SKIP,
                          f"/oauth2/start answered {start.status} without cookies"))
    health = Target(t.base, t.timeout).request("GET", "/api/health")
    out.append(Result("health endpoint reveals no data", PASS if len(health.body) < 200
                      else WARN, f"{health.status}, {len(health.body)} bytes"))
    return out


def run(target: Target, *, team: bool, write: bool) -> list[Result]:
    checks: list[Check] = [check_transport, check_surface, check_csrf, check_body_limit]
    if team:
        checks.append(check_team)
    else:
        checks.insert(0, check_headers)
        if write:
            checks.append(check_workspace)
    results: list[Result] = []
    for check in checks:
        try:
            results.extend(check(target))
        except OSError as exc:
            results.append(Result(check.__name__, FAIL, f"connection error: {exc}"))
    return results


def markdown(base: str, results: list[Result]) -> str:
    lines = [f"# Security self-test – {base}", "", "| Check | Result | Detail |",
             "|-------|--------|--------|"]
    lines += [f"| {r.check} | {r.outcome} | {r.detail.replace('|', '/')} |" for r in results]
    counts = {o: sum(1 for r in results if r.outcome == o) for o in (PASS, WARN, FAIL, SKIP)}
    lines += ["", " · ".join(f"{k}: {v}" for k, v in counts.items()), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url", help="base URL of the workbench")
    ap.add_argument("--team", action="store_true", help="team deployment behind the SSO proxy")
    ap.add_argument("--no-write", action="store_true", help="do not create a sample workspace")
    ap.add_argument("--report", help="also write the results as Markdown to this file")
    args = ap.parse_args(argv)
    results = run(Target(args.url), team=args.team, write=not args.no_write)
    width = max(len(r.check) for r in results)
    for r in results:
        print(f"{r.outcome:4}  {r.check:{width}}  {r.detail}")
    if args.report:
        Path(args.report).write_text(markdown(args.url, results), encoding="utf-8")
    failed = [r for r in results if r.outcome == FAIL]
    print(f"\n{len(results)} checks, {len(failed)} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
