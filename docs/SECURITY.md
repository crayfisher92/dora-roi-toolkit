# Security design and threat model

The toolkit processes **confidential client data**: the full inventory of a financial
entity's ICT contracts, providers, costs, critical functions and exit plans. This document
describes what we protect, against whom, and how each threat is mitigated and tested. The
vulnerability-disclosure policy is in [`/SECURITY.md`](../SECURITY.md).

## Scope and deployment assumptions

| Mode | Description | Security posture |
|---|---|---|
| **CLI / Python library** | Runs on the consultant's machine against local files. | Same trust as any local tool; protections against malicious *input files* apply. |
| **Workbench, local** (`roi serve`, `docker compose up`) | Single user, bound to `127.0.0.1`. | Default and recommended. Browser-borne attacks (CSRF, clickjacking, XSS) are still mitigated because other websites run in the same browser. |
| **Workbench, shared** (team server) | Several users reach one instance. | Supported only **behind the organisation's reverse proxy with authentication (SSO) and TLS**. The app adds session isolation but has no accounts of its own. |

Out of scope: hosting on the public internet without authentication; multi-tenant SaaS.

## Assets

| Asset | Where | Confidentiality | Integrity |
|---|---|---|---|
| Register data (contracts, providers, costs, functions) | uploads, workspace memory, project files, exports | High | High (it is filed with the supervisor) |
| Audit trail (who changed what) | workspace change log, project file, CSV export | Medium | High (evidence for internal audit) |
| Justifications for accepted findings | workspace, reports | Medium | High |
| Generated reports (validation, CRO summary, xBRL-CSV) | downloads | High | High |

## Actors

* **Consultant / risk manager** – legitimate user; trusted with the data they upload.
* **Other user of a shared instance** – must not see or change someone else's workspace.
* **Malicious website** visited in the same browser – may try CSRF, framing, or reading
  responses.
* **Malicious or malformed input file** – client-supplied spreadsheets, zips and CSVs are
  untrusted (decompression bombs, XML attacks, formulas, oversized tables, odd file names).
* **Compromised dependency** – supply-chain risk in PyPI packages and the base image.
* **Anyone with access to logs or the container host.**

## Trust boundaries

1. Browser ⇄ workbench HTTP interface.
2. Uploaded / opened file ⇄ parsers (python-calamine, csv, zipfile, json, sqlite3).
3. Workbench ⇄ local filesystem (temporary files, SQLite project files, exports).
4. Container ⇄ host (Docker).
5. Build ⇄ third-party packages (PyPI, Docker Hub).

## STRIDE analysis

| # | STRIDE | Threat | Mitigation | Verified by |
|---|---|---|---|---|
| T1 | **S**poofing | Another user of a shared instance opens a workspace by guessing or harvesting its ID. | 128-bit random workspace IDs; workspaces owned by a 256-bit browser session (HttpOnly, SameSite=Strict cookie); other sessions get 404; workspace list shows only own workspaces. Authentication of *people* is delegated to the reverse proxy (deployment assumption). | `test_sessions_are_isolated`, `test_workspace_ids_are_unguessable` |
| T2 | **S**poofing | A malicious site submits forms to the app in the user's browser (CSRF). | `SameOriginMiddleware`: state-changing requests must come from the same origin (`Sec-Fetch-Site`, else `Origin`/`Referer`); session cookie `SameSite=Strict`. | `test_cross_site_posts_are_rejected` |
| T3 | **T**ampering | Uploaded spreadsheet contains formulas that execute when an exported workbook is opened (CSV/formula injection, CWE-1236). | Exported workbooks write every text value as a literal string with quote prefix; the human-oriented audit CSV neutralises `= + - @`; machine CSV/xBRL-CSV keep values verbatim by design (D-035). | `test_excel_export_never_writes_formulas`, `test_csv_safe` |
| T4 | **T**ampering | Unauthorised or untraceable edits to a register before submission. | Append-only change log (who, when, old → new, and every export with the register's state), versions, CSV export; errors cannot be "accepted", only fixed; acceptances require a justification and are logged. | `test_audit_trail_page_and_csv`, `test_accept_warning_but_not_error` |
| T5 | **T**ampering | Zip members with `../` paths overwrite files (path traversal / zip-slip). | Archives are never extracted to disk: members are read in memory and only their base name is used to recognise templates; uploads are stored under fixed names in a private temporary directory; exports write only toolkit-generated paths. | `test_zip_slip_member_names_are_ignored` |
| T6 | **T**ampering | Malicious XML inside `.xlsx` (XXE, billion laughs). | Workbooks are read with python-calamine (Rust, memory-safe), whose XML parser rejects DTDs and custom entities: such files fail with an error and nothing is expanded or fetched. openpyxl is no longer a runtime dependency (D-045). | `test_xml_entity_attacks_are_rejected` |
| T7 | **R**epudiation | A user denies having changed or accepted something. | Audit trail entries carry user name, UTC timestamp and old/new values; exported as CSV and stored in project files. The user name is self-declared (no accounts) – attribution is as strong as the proxy authentication in front of the app. | `test_audit_trail_page_and_csv` |
| T8 | **I**nformation disclosure | Client data in logs (request URLs with search terms, workspace IDs). | No application logging of data; uvicorn access log and `Server` header disabled by default (`--access-log` to opt in); no telemetry, no outbound network calls (verified by code search; Docker image needs no egress at runtime). | `test_serve_disables_access_log`, code search in CI review |
| T9 | **I**nformation disclosure | Data leaks through the browser: caching, referrers, framing by another site, third-party scripts. | `Cache-Control: no-store` on workspace pages; `Referrer-Policy: same-origin`; `X-Frame-Options: DENY` and `frame-ancestors 'none'`; strict CSP (`script-src 'self'`, no inline script, no third-party origins); `Cross-Origin-Opener/Resource-Policy: same-origin`. | `test_security_headers`, E2E `test_no_csp_violations` |
| T10 | **I**nformation disclosure | XSS through client-supplied values rendered in pages and reports. | Jinja2 autoescaping everywhere; SVG/chart labels escaped; strict CSP as defence in depth; downloadable HTML reports get a CSP without network access. | `test_report_renderers`, CSP tests |
| T11 | **I**nformation disclosure | Data persists on disk after use. | Uploads are parsed from temporary files deleted immediately; workspaces live in memory unless the user saves a project file or enables the projects folder (opt-in); project files are written with mode 0600; Docker container has a read-only root filesystem and `tmpfs` for `/tmp`. | `test_roundtrip_is_exact`, Docker smoke test |
| T17 | **T**ampering / **E**levation | A crafted project file (SQLite) received from a third party exploits the loader. | Read-only connection, `trusted_schema=OFF`, `cell_size_check`, `quick_check`, size limit, required tables must be real tables (no views/triggers executed), strict format version, typed value decoding; only plain `SELECT`s; fresh workspace id on open; projects-folder opening accepts only listed file names. | `test_rejects_tampered_files`, `test_rejects_non_projects`, `test_projects_folder_autosave_and_reopen` |
| T18 | **I**nformation disclosure | The PDF renderer is made to fetch a URL or read a local file referenced in report content (SSRF, local file disclosure). | Reports are self-contained; WeasyPrint gets a URL fetcher that refuses every URL (no network, no `file://`); client values are HTML-escaped before rendering. | `test_external_resources_are_never_fetched` |
| T12 | **D**enial of service | Decompression bomb or oversized table pins CPU/memory. | 25 MB upload limit; archive limits on total uncompressed size (200 MB), file count and compression ratio; row cap per table (100 000, configurable). | `test_row_limit_rejects_huge_table`, `test_archive_size_limit` |
| T13 | **D**enial of service | Many or very large workspaces exhaust memory. | Bounded LRU store: at most 20 workspaces / wizards **and** a total row budget (`ROI_MAX_STORE_ROWS`, default 500 000 ≈ 1 GB) – least recently used first. | `test_store_eviction`, `test_store_evicts_by_row_budget` |
| T19 | **D**enial of service | Parallel PDF exports exhaust CPU and memory. | At most `ROI_MAX_PDF_JOBS` (2) renders at once; others wait up to 60 s, then 503 with `Retry-After`. | `test_concurrent_renders_are_limited` |
| T14 | **E**levation of privilege | Open redirect used for phishing via a trusted local URL. | `safe_next` only accepts same-site paths (no scheme, host, `//`, `\`, control characters). | `test_safe_next` |
| T15 | **E**levation of privilege | Container escape / host impact. | Non-root user, read-only root filesystem, all capabilities dropped, `no-new-privileges`, port published on `127.0.0.1` only. | CI Docker smoke test |
| T16 | Supply chain | Vulnerable or malicious dependency. | Minimal dependency set; CI runs `pip-audit` (known vulnerabilities) and `bandit` (SAST) on every push; Docker base image is the official slim Python image. | CI jobs `security` |

## Residual risks and recommendations

* **No authentication in the app.** On shared deployments put it behind SSO/TLS; user names
  in the audit trail are self-declared.
* **Project files are not encrypted.** They contain the full register; store them like any
  other confidential client file (encrypted disk, DMS with access control).
* **xBRL-CSV and CSV exports are verbatim.** Opening them in a spreadsheet application can
  evaluate formulas contained in client data; use the Excel export for human review.
* **Automated scanning is not a penetration test.** Commission one before a shared
  production deployment.
