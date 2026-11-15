# Running the workbench for a team

By default the workbench is a single-user tool: it listens on `127.0.0.1`, has no login and
identifies browsers by an anonymous session cookie. For a team it runs behind a
**single-sign-on proxy**. The reference set-up is
[oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/) signing users in with
**Microsoft Entra ID**, with TLS terminated in front of it. The proxy forwards the signed-in
user's e-mail address in a request header, and the workbench trusts that header only on
connections from the proxy.

```
browser ──TLS──▶ load balancer / ingress ──▶ oauth2-proxy (Entra ID) ──▶ workbench
                                              sets X-Forwarded-Email       trusts it only
                                                                           from the proxy
```

A ready-to-use example is in [`deploy/team/`](../deploy/team/), with a
`docker-compose.yml` and `.env.example`.

## What team mode changes

| | Local mode (default) | Team mode (`ROI_AUTH_HEADER` set) |
|---|---|---|
| Who is the user | The browser session; the name in the audit trail is self-declared | The user signed in by the proxy; the audit trail records their e-mail address and the name form is gone |
| Requests without a sign-in | Allowed | `401`; requests that bypass the proxy get `403` (`/api/health` stays open for probes) |
| Workspaces | Belong to the browser session | Belong to the user and follow them across browsers |
| Projects folder (`ROI_PROJECTS_DIR`) | One folder | `users/<user>/` (private, per user) and `team/` (shared) |
| Editing a project | One editor per project file | The same, across users: others get a **read-only** view while someone edits |
| Memory | Shared budget | Shared budget plus a per-user share, so one user cannot push everyone else's work out |

These apply in both modes:
- Parsing, validation and saving run in worker threads, so a large upload doesn't block other users.
- Request bodies over 26 MB are refused before they are read.

## Settings

| Variable / `roi serve` option | Default | Meaning |
|---|---|---|
| `ROI_AUTH_HEADER` / `--auth-header` | *(unset: local mode)* | Header with the signed-in user, e.g. `X-Forwarded-Email` |
| `ROI_TRUSTED_PROXIES` / `--trusted-proxy` | `127.0.0.1,::1` | IP addresses or networks of the proxy; the header is ignored from anywhere else |
| `ROI_PROJECTS_DIR` / `--projects` | *(unset: nothing saved)* | Projects folder with the private and team spaces; **back it up** |
| `ROI_LOCK_MINUTES` | `30` | Inactivity after which a colleague may take over a project's edit lock |
| `ROI_MAX_WORKSPACES` | `20` | Workspaces held in memory in total |
| `ROI_MAX_STORE_ROWS` | `500000` | Rows held in memory in total (about 1 GB) |
| `ROI_MAX_USER_WORKSPACES` | `10` | Workspaces per user |
| `ROI_MAX_USER_ROWS` | `200000` | Rows per user |
| `ROI_MAX_PARALLEL_JOBS` | `4` | Imports, project loads and edits processed at the same time |
| `ROI_GLEIF` | *(unset: off)* | `1` shows *Check LEIs with GLEIF* on the Fix page; the server then needs outbound HTTPS to `api.gleif.org` (proxy via `HTTPS_PROXY`). Sends only LEIs |
| `ROI_SECURE_COOKIES` | *(unset)* | `1` marks cookies `Secure` in local mode too, when the workbench is served over HTTPS by a proxy; always on in team mode |

Raise `ROI_MAX_WORKSPACES` and `ROI_MAX_STORE_ROWS` with the team size and the container's
memory. A workspace evicted from memory is not lost if it lives in the projects folder: it
was autosaved after every change.

## Setting it up with Entra ID

1. **Register an application** in Entra ID (App registrations → New registration):
   - Redirect URI (Web): `https://<your-host>/oauth2/callback`.
   - Create a client secret.
   - Note the tenant ID, client ID and secret.
   - To limit access to a group, add a `groups` claim to the ID token and use `OAUTH2_PROXY_ALLOWED_GROUPS` with the group's object ID.
   - oauth2-proxy uses its `entra-id` provider with PKCE and the scopes `openid email profile`.
     The workbench identifies users by e-mail; for accounts without a mailbox set
     `OAUTH2_PROXY_OIDC_EMAIL_CLAIM=preferred_username` (the UPN).
2. **Fill in** `deploy/team/.env` from `.env.example`. Generate the cookie secret with
   `python -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.
3. **Start** with `docker compose --env-file .env up -d` in `deploy/team/`.
4. **Put TLS in front** of port 4180 (company load balancer, ingress or reverse proxy). Without TLS the
   sign-in cookie and the register data travel in clear text.
5. **Check** with the sign-in test protocol [`ENTRA_SIGNIN_TEST.md`](ENTRA_SIGNIN_TEST.md)
   (automated self-test plus 13 manual steps, about 45 minutes). In short:
   - `https://<your-host>/` asks for the Entra sign-in.
   - After signing in, the header shows *Signed in: …* with a *Sign out* link.
   - Calling the workbench container directly is refused with `403`.

The same oauth2-proxy settings are tested on every pull request against a mock Entra ID
(`compose.ci-mock.yml`, [`SECURITY_TESTING.md`](SECURITY_TESTING.md)).

## Why the header can be trusted

- The workbench container publishes no port. Only oauth2-proxy can reach it, on a fixed
  address in a private network, and `ROI_TRUSTED_PROXIES` names exactly that address. Any
  other client sending `X-Forwarded-Email` gets `403`.
- oauth2-proxy replaces any `X-Forwarded-Email` / `X-Forwarded-User` sent by the browser with
  the signed-in user's. Keep `skip_auth_strip_headers` at its default (`true`).
- The workbench does not evaluate `X-Forwarded-For`; `roi serve` runs uvicorn with
  `proxy_headers=False`. The client address it checks is the proxy's own.

## Operating notes

- **Run one process.** Workspaces and edit locks live in the process's memory. Scale up
  (CPU, memory, `ROI_MAX_*`), not out to several replicas or uvicorn workers.
- **Edit locks:**
  - Opening a project takes its edit lock. *Close and release* on the overview frees it; so
    does evicting the workspace from memory, or 30 minutes without activity.
  - Whoever opens a locked project gets a read-only view.
  - If a lock expires and a colleague takes over, the first user's next change is refused
    and their view becomes read-only.
- **No silent overwrites.** Before every autosave the workbench checks that the file hasn't
  changed on disk since it was read. If it has, for example through a restore from backup
  or another instance, the workspace is saved as `<name>-conflict-<timestamp>.roiproj` next
  to it, and the user is told.
- **Moving between spaces.** *Move to team space* on the overview moves a project from the
  private space to the team space. Users exchange project files outside the tool by
  downloading and uploading them.
- **Data protection.** The projects folder holds complete registers and is not encrypted by
  the application. Use an encrypted volume with backups and restricted administrator access.
