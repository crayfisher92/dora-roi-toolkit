# Security testing

The workbench processes confidential register data (contracts, costs, providers, critical
functions). This page describes the automated security self-test that runs on every pull
request, what it found, and the scope for the **external penetration test** to be done before
production use. Threat model and hardening measures: [`SECURITY.md`](SECURITY.md); team
set-up: [`TEAM_DEPLOYMENT.md`](TEAM_DEPLOYMENT.md).

## 1. Automated self-test (every pull request and release)

CI job *Security self-test, ZAP scan and sign-in* (`.github/workflows/ci.yml`, job `dast`)
builds the Docker image and tests it as deployed:

| Step | What it checks |
|------|----------------|
| `scripts/security_selftest.py` on the container (local mode) | security headers (CSP, frame, MIME sniffing, referrer), no server banner, no API docs, TRACE refused, path traversal on `/static`, errors without stack traces, cross-site POSTs refused (Origin, Referer, Sec-Fetch-Site), 10 GiB upload refused before it is read, unguessable workspace ids bound to the browser session, reflected input escaped, online LEI check off by default |
| OWASP ZAP baseline scan | passive scan of all pages ZAP can reach; the job fails on the alerts marked `FAIL` in [`.zap/rules.tsv`](../.zap/rules.tsv) (missing headers, cookie flags, cross-domain scripts, error disclosure); the full report is a build artifact (`zap-baseline`) |
| Team stack: oauth2-proxy **with the production settings** + mock Entra ID ([`deploy/team/compose.ci-mock.yml`](../deploy/team/compose.ci-mock.yml)) | `scripts/sso_check.py`: anonymous users are sent to sign-in; the authorisation-code flow with PKCE completes; the workbench shows the signed-in user; a forged `X-Forwarded-Email` is replaced by the proxy; a workspace is not reachable without signing in; cross-site POSTs are refused for signed-in users; sign-out ends the session. `security_selftest.py --team`: forged identity headers never reach the workbench, sign-in cookies are `Secure`, `HttpOnly`, `SameSite`. The workbench container publishes no port. |

Unit and route tests cover the same ground from the inside: `tests/test_security.py` (XSS,
zip-slip, no outbound network code except the opt-in GLEIF check), `tests/test_hardening.py`
(CSRF, headers, size limits, XML entity attacks, formula injection), `tests/test_team.py`
(trusted-proxy identity, spaces, locks, cookie flags), `tests/test_fuzz.py` (parser fuzzing),
and bandit and pip-audit in CI.

Run the self-test against any instance (it creates one sample workspace unless `--no-write`):

```bash
python scripts/security_selftest.py https://roi.example.com --team --no-write --report selftest.md
```

### Findings of the first run (fixed in v0.2.0)

| # | Finding | Risk | Fix |
|---|---------|------|-----|
| S-1 | `/docs`, `/redoc` and `/openapi.json` (FastAPI defaults) were public: they listed every route and Swagger UI loads scripts from a CDN | Low – information disclosure, third-party script | Switched off (`create_app`), test `test_no_interactive_api_docs` |
| S-2 | Behind the TLS-terminating proxy the app sees HTTP, so the session cookie never got the `Secure` flag in team mode; the `lang` and `roi_user` cookies never had it, `lang` was readable by scripts | Medium – cookie could travel over plain HTTP if a user opened an `http://` link | `Secure` always in team mode (or `ROI_SECURE_COOKIES=1`), `HttpOnly` on all cookies; test `test_cookies_are_secure_behind_the_tls_proxy` |
| S-3 | `.docx` extraction refused a DTD only in the first 4 KiB of a document part | Low – stdlib parser resolves no external entities | DTD refused anywhere (Phase 5) |
| S-4 | oauth2-proxy pinned to v7.7.1 (two years old) with the generic OIDC provider and no PKCE | Medium – missed security fixes | v7.15.6, provider `entra-id`, PKCE (`S256`), 8 h session, `SameSite=Lax` |

Accepted (documented, not changed): the CSP allows inline *styles* (`style-src 'unsafe-inline'`,
needed by the server-rendered reports; inline *scripts* are not allowed); CSRF protection uses
Origin / Sec-Fetch-Site checks instead of tokens (ZAP rule 10202 ignored); in local mode the
workbench has no login – it binds to `127.0.0.1` and is for one person.

## 2. External penetration test – scope

To be commissioned before the workbench holds production data. Suggested brief for the
tester:

**Target.** The team deployment as in `deploy/team/` on a staging host with TLS: oauth2-proxy
(Entra ID) → workbench container (read-only root, no capabilities, non-root) → project files on
a volume. Version: the release candidate tag (e.g. `v0.2.0-rc.1`), image from
`ghcr.io/crayfisher92/dora-roi-toolkit`.

**Accounts.** Three test users in a test tenant (or test accounts in the client tenant):
two members of the allowed group (to test isolation between users) and one outside it (to
test the group restriction). Synthetic data only – the Alpenrand sample (`roi sample`) and
large generated registers (the generator used by `scripts/profile_large.py`).

**In scope.**

1. Authentication and session: bypass of oauth2-proxy, identity-header injection (incl.
   case variants, duplicates, `X-Forwarded-*` family, hop-by-hop tricks), session fixation,
   sign-out, cookie scope.
2. Authorisation: access to another user's private space, workspaces, project files,
   downloads and audit trail (IDOR on `/w/{id}/…`, project names, lock take-over); actions on
   a read-only (locked) workspace.
3. Input handling: uploads (Excel, CSV, ZIP, xBRL-CSV packages, project files, DOCX/PDF
   contracts): zip bombs, path traversal, XML attacks, formula injection in exports, malformed
   SQLite project files; XSS in every field that is rendered (register values, comments,
   contract evidence, incident text, file names) including the HTML/PDF reports.
4. CSRF and clickjacking on all state-changing routes.
5. Denial of service within reason: large uploads, many workspaces per user, slow requests
   (limits: `ROI_MAX_*` settings).
6. Container and deployment: escape from the read-only container, secrets in the image,
   exposed ports, TLS configuration of the staging ingress.
7. The opt-in GLEIF lookup (`ROI_GLEIF=1`): SSRF or response injection.

**Out of scope.** Entra ID itself and the client's tenant policies (MFA, conditional
access); denial-of-service floods; social engineering.

**Rules of engagement.** Staging only, agreed time window, findings rated with CVSS 4.0,
re-test of high and critical findings included. Report findings privately as described in
[`SECURITY.md`](../SECURITY.md).

**What the tester gets.** This page, `SECURITY.md`, `TEAM_DEPLOYMENT.md`, the source code
(grey box) and the latest CI self-test and ZAP reports.
