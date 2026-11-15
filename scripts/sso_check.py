#!/usr/bin/env python3
"""End-to-end sign-in check of a team deployment with a non-interactive identity provider.

Used in CI against oauth2-proxy + a mock Entra ID (``deploy/team/compose.ci-mock.yml``):
signs in through the real authorisation-code flow, then checks that the workbench sees the
signed-in user, that a forged identity header cannot change it, that the user can work, and
that signing out ends the session. Standard library only.

    python scripts/sso_check.py http://localhost:4180 --expect-user anna.muster@example.com

A real Entra ID tenant needs an interactive sign-in (MFA, conditional access): follow
``docs/ENTRA_SIGNIN_TEST.md`` instead and run ``security_selftest.py --team`` for the
anonymous checks.
"""

from __future__ import annotations

import argparse
import http.client
import re
import sys
import urllib.parse
from dataclasses import dataclass, field


@dataclass
class Browser:
    """A minimal browser: per-host cookie jar, manual redirects."""

    jar: dict[str, dict[str, str]] = field(default_factory=dict)
    timeout: float = 20.0

    def request(self, method: str, url: str, *, headers: dict[str, str] | None = None,
                body: bytes | None = None) -> tuple[int, dict[str, str], bytes]:
        parts = urllib.parse.urlsplit(url)
        conn_cls = (http.client.HTTPSConnection if parts.scheme == "https"
                    else http.client.HTTPConnection)
        conn = conn_cls(parts.netloc, timeout=self.timeout)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        hdrs = {"User-Agent": "dora-roi-sso-check", "Accept": "text/html"}
        cookies = self.jar.get(parts.netloc, {})
        if cookies:
            hdrs["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
        hdrs.update(headers or {})
        try:
            conn.request(method, path, body=body, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read(5_000_000)
            out = {k.lower(): v for k, v in resp.getheaders()}
            for k, v in resp.getheaders():
                if k.lower() == "set-cookie":
                    name, _, rest = v.partition("=")
                    value = rest.split(";", 1)[0]
                    if "max-age=0" in v.lower() or "expires=thu, 01 jan 1970" in v.lower():
                        self.jar.setdefault(parts.netloc, {}).pop(name.strip(), None)
                    else:
                        self.jar.setdefault(parts.netloc, {})[name.strip()] = value
        finally:
            conn.close()
        return resp.status, out, data

    def get(self, url: str, *, headers: dict[str, str] | None = None,
            max_hops: int = 10) -> tuple[int, str, bytes]:
        """GET following redirects; returns the final status, URL and body."""
        for _ in range(max_hops):
            status, hdrs, data = self.request("GET", url, headers=headers)
            if status in (301, 302, 303, 307, 308) and "location" in hdrs:
                url = urllib.parse.urljoin(url, hdrs["location"])
                continue
            return status, url, data
        raise RuntimeError(f"too many redirects, last {url}")


def check(base: str, user: str) -> list[tuple[str, bool, str]]:
    base = base.rstrip("/")
    origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(base))
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))

    b = Browser()
    status, hdrs, _ = b.request("GET", base + "/")
    record("anonymous request is sent to sign-in", status in (302, 303, 401, 403),
           f"{status} {hdrs.get('location', '')[:80]}")

    status, final, page = b.get(base + "/")
    text = page.decode("utf-8", "replace")
    record("sign-in completes and the workbench opens", status == 200 and final.startswith(base),
           f"{status} {final[:80]}")
    record("workbench shows the signed-in user", user in text, user)

    status, _, forged = b.get(base + "/", headers={"X-Forwarded-Email": "mallory@evil.example"})
    record("forged X-Forwarded-Email is replaced by the proxy",
           status == 200 and "mallory@evil.example" not in forged.decode("utf-8", "replace")
           and user in forged.decode("utf-8", "replace"), str(status))

    status, hdrs, _ = b.request("POST", base + "/sample", body=b"variant=clean", headers={
        "Origin": origin, "Content-Type": "application/x-www-form-urlencoded"})
    location = urllib.parse.urljoin(base + "/", hdrs.get("location", ""))
    record("signed-in user can create a workspace", status == 303 and "/w/" in location,
           f"{status} {location[-40:]}")
    if "/w/" in location:
        s, _, _ = b.get(location + "/fix")
        record("workspace opens for its owner", s == 200, str(s))
        # one request without following redirects: the mock IdP signs every browser in
        s, hdrs, _ = Browser().request("GET", location)
        record("workspace is not reachable without signing in", s != 200,
               f"{s} {hdrs.get('location', '')[:60]}")

    status, _, _ = b.request("POST", base + "/sample", body=b"variant=clean", headers={
        "Origin": "https://evil.example", "Content-Type": "application/x-www-form-urlencoded"})
    record("cross-site POST rejected for a signed-in user", status == 403, str(status))

    b.get(base + "/oauth2/sign_out")
    status, hdrs, _ = b.request("GET", base + "/")
    record("sign-out ends the session", status in (302, 303, 401, 403), str(status))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url", help="public URL of oauth2-proxy")
    ap.add_argument("--expect-user", required=True, help="e-mail the IdP signs in")
    args = ap.parse_args(argv)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+", args.expect_user):
        ap.error("--expect-user must be an e-mail address")
    results = check(args.url, args.expect_user)
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:{width}}  {detail}")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results)} checks, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
