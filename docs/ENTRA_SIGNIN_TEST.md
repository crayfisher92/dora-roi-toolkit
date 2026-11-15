# Entra ID sign-in test (real tenant)

CI tests the sign-in end to end with oauth2-proxy and a **mock** Entra ID
([`SECURITY_TESTING.md`](SECURITY_TESTING.md)). This protocol is the one-off test against
**your** tenant before the pilot: about 45 minutes, done by the person who set up the app
registration plus two pilot users. Record the result in the table at the end and keep it with
the pilot documentation.

## Before you start

- The team stack runs on the pilot host as described in
  [`TEAM_DEPLOYMENT.md`](TEAM_DEPLOYMENT.md), behind TLS, from the release candidate image.
- App registration: redirect URI `https://<host>/oauth2/callback`, client secret, and – if
  access is limited to a group – the *groups* claim in the ID token and
  `OAUTH2_PROXY_ALLOWED_GROUPS` set to the group's object ID.
- Three accounts: **A** and **B** in the allowed group, **C** outside it (or from an
  e-mail domain not in `ALLOWED_EMAIL_DOMAINS`).
- A private browser window per account.

## Automated part (2 minutes, no sign-in needed)

```bash
python scripts/security_selftest.py https://<host> --team --no-write --report entra-selftest.md
```

Expected: no `FAIL`. `HSTS` and *HTTP redirects to HTTPS* depend on your ingress – fix them
there if they show `WARN` or `FAIL`.

## Manual part

| # | Step | Expected |
|---|------|----------|
| 1 | Open `https://<host>/` as **A** | Redirect to the Microsoft sign-in page of your tenant (your branding, MFA / conditional access as per tenant policy) |
| 2 | Sign in as **A** | The workbench opens; the header shows *Signed in: A's e-mail* |
| 3 | `https://<host>/oauth2/userinfo` as **A** | JSON with A's e-mail. If `email` is empty, the account has no mail attribute: set `OAUTH2_PROXY_OIDC_EMAIL_CLAIM=preferred_username` and repeat from 1 |
| 4 | As **A**: *Clean sample* (home page), change one value, save the project in **My projects** | Saved; audit trail shows the change under A's e-mail |
| 5 | Sign in as **B** in another window | B's header shows B's e-mail; **My projects** of B does *not* list A's project |
| 6 | As **B**: copy the address of A's workspace (from step 4) into B's window | *Not found* – workspaces belong to the user who opened them |
| 7 | As **A**: save a project in **Team projects**; as **B**: open it | B sees it; B can open it read-only while A is editing (lock notice with A's name) |
| 8 | As **A**: *Close and release*; as **B**: edit the project | B can edit now; the audit trail shows both users |
| 9 | Sign in as **C** | Refused by oauth2-proxy (403 / *not authorised*) – the workbench is never shown |
| 10 | As **A**: *Sign out* in the header, then open `https://<host>/` | Sign-in page again (the Microsoft session may sign A in silently – that is the tenant's single sign-on, not the workbench) |
| 11 | From a machine on the host network: `curl http://<workbench-container>:8000/` with header `X-Forwarded-Email: a@<domain>` | `403` – the workbench only trusts oauth2-proxy's address |
| 12 | Wait 8 hours after A's sign-in (or set `OAUTH2_PROXY_COOKIE_EXPIRE=5m` for the test) | Next click goes through the sign-in again |
| 13 | Disable account **B** in Entra ID, wait for B's cookie to expire (step 12) | B cannot sign in again |

## Result

| Item | Result | By / date |
|------|--------|-----------|
| Automated self-test – no FAIL | | |
| Steps 1–3 sign-in and claims | | |
| Steps 4–8 user isolation, team space, locks | | |
| Step 9 group / domain restriction | | |
| Steps 10–13 sign-out, direct access, expiry, disabled account | | |
| Deviations and fixes | | |

Typical problems: *redirect URI mismatch* (the URI must match exactly, including
`https://`); *email not verified* does not occur with Entra ID (oauth2-proxy accepts tokens
without the `email_verified` claim); an empty e-mail (step 3); clock skew on the host (sign-in
loops – check NTP).
