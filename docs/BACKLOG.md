# Backlog (review → backlog → implement cycles)

Each cycle is a critical self-review from two perspectives – **SE** (senior engineer: security,
correctness, performance, maintainability) and **TPR** (a bank's Head of Third-Party Risk:
does the tool support the decisions and evidence I need?). Every finding was reproduced
before being recorded; the *Evidence* column says how. Severity: **High** = wrong or
misleading result, or exploitable; **Medium** = significant gap or risk in normal use;
**Low** = polish. The cycle continues until no High or Medium item is open.

Status: ✅ done · 🔄 in progress · ⏳ open · ➖ won't do (with reason)

## Cycle 1

| ID | Sev. | View | Finding | Evidence | Status |
|---|---|---|---|---|---|
| B-01 | High | SE | **Spreadsheet formula injection.** Client-supplied text starting with `=`, `+`, `-`, `@` is written to exported workbooks as a live formula (e.g. a provider named `=HYPERLINK(…)`). | openpyxl stored the cell with `data_type='f'`. | ✅ Excel cells forced to literal strings + quote prefix; audit CSV neutralised (`test_excel_export_never_writes_formulas`) |
| B-02 | High | SE | **Decompression / size DoS.** A 50 KB zip expanding to 5 M CSV rows kept the server busy for > 2 min; no limit on uncompressed size or row count. | Upload test ran past the 120 s timeout. | ✅ `io/limits.py`: uncompressed-size, file-count and compression-ratio guards on every zip/xlsx; row cap per table (env-tunable); web shows the reason |
| B-03 | High | TPR | **Provider page understates dependency.** Only functions supported *directly* are counted; dependencies through subcontracting are ignored – exactly the "what if this provider fails" question. | Nimbus Cloud Inc.: 1 critical function shown, 16 depend on it via supply chains. | ✅ `analytics/impact.py`; provider page *Failure impact* table and flag; `critical_functions_incl_indirect` per provider/group; key message counts indirect dependencies |
| B-04 | Medium | SE | **Open redirect.** `next=/\evil.example` passes the local-target check; browsers treat `/\` like `//`. | `_safe_next("/\\evil.com")` returned the target unchanged. | ✅ `web/security.safe_next` rejects `//`, `\\`, control characters and any host |
| B-05 | Medium | SE | **Cross-site request forgery.** State-changing POSTs are accepted from any origin. | POST with `Origin: http://evil.example` → 303. | ✅ `SameOriginMiddleware` (Origin / Referer / Sec-Fetch-Site) |
| B-06 | Medium | SE | **No security headers** (CSP, frame-ancestors / X-Frame-Options, nosniff, Referrer-Policy) – clickjacking and content sniffing possible. | Response headers empty. | ✅ `SecurityHeadersMiddleware`: strict CSP (no inline script on app pages), frame-ancestors none, nosniff, no-referrer, COOP/CORP, `Cache-Control: no-store` |
| B-07 | Medium | SE | **defusedxml not a declared dependency.** openpyxl only guards against malicious XML (billion laughs, XXE) when defusedxml is installed; the Docker image did not guarantee it. | Present locally by accident, absent from `pyproject.toml`. | ✅ `defusedxml` declared; test asserts openpyxl uses it |
| B-08 | Medium | SE | **Edit latency grows with register size**: 1.9 s per cell edit at 3 000 B_02.02 rows – code-list lookups re-normalise every label on each call (2.2 s of 3.8 s parse) and every version deep-copies the register (1.1 s). | cProfile of `Workspace.edit` on the sample ×20. | ✅ cached code-list lookups, incremental re-parse, versions as change-log positions: edit 1.9 s → 0.45 s, load 1.7 s → 0.9 s at 3 000 rows |
| B-09 | Medium | SE | **No locking around workspace mutations.** FastAPI runs sync handlers in a thread pool; two concurrent saves can interleave raw-value updates, version snapshots and derived-state invalidation. | Code inspection (`Workspace.edit` / `_derive` unsynchronised). | ✅ re-entrant lock around all mutations and derived state; concurrency test with 8 threads |
| B-10 | Medium | TPR | **Diff is dominated by administrative changes.** Annual reassessment dates make every function "changed", hiding material changes (criticality, provider, cost, end date). | 31 of 31 changed B_06.01 rows differ only in c0070. | ✅ administrative fields and < 10 % amount changes separated; compare page shows material changes, toggle for all |
| B-11 | Medium | TPR | **No audit trail as evidence.** Changes are kept but cannot be seen with old → new values or exported; an internal auditor asks "who changed what and when". | Versions page lists labels only. | ✅ append-only change log with user and timestamp; *Audit trail* page and CSV export; user name via cookie |
| B-12 | Medium | TPR | **No way to accept a finding with justification.** Legitimate findings (e.g. XRF-014 – parent outside the EU scope) stay open forever and depress the score. | No waiver mechanism. | ✅ accept warnings/info with justification (errors cannot be accepted); accepted list with reopen; excluded from score |
| B-13 | Medium | TPR | **Work is lost on restart.** In-memory only; no way to save a workspace (data, versions, justifications) and reopen it. | By design (D-023) but blocks year-round use. | ➖ superseded by production-hardening item H-2 (SQLite project files) |
| B-14 | Medium | TPR | **Duplicate providers are not detected.** The same provider registered twice under different codes (LEI vs EUID, typo) splits concentration figures. | No rule compares provider names. | ✅ rule `BUS-025 Possible duplicate provider` (name normalised for case, accents, legal forms) |
| B-15 | Low | SE | Language switch drops the current query string (e.g. the selected template on the Fix page). | Manual check. | ⏳ |
| B-16 | Low | TPR | Findings cannot be exported as a spreadsheet to send to business owners. | Only HTML / Markdown / JSON. | ⏳ |
| B-17 | Low | TPR | Per-finding validator messages are English only (D-030). | — | ⏳ |

## Cycle 2

| ID | Sev. | View | Finding | Evidence | Status |
|---|---|---|---|---|---|
| B-18 | High | SE | **No session isolation.** Any browser lists every workspace on the home page and can open it – on a shared deployment one consultant sees another client's register. | Second TestClient saw and opened the first one's workspace (200). | ✅ `SessionMiddleware`: random HttpOnly/SameSite=Strict session cookie; workspaces and wizards owned by their session, 404 for others; 128-bit IDs |
| B-19 | Medium | SE | **A crashing rule leaves the register "Ready".** Readiness only counts errors; `rule_failures` are not reflected in the score, status or UI. | Injected exception into BUS-001 → readiness `ready`. | ✅ readiness `not_ready` and a banner in the workbench and HTML report when any rule failed |
| B-20 | Medium | SE | **Access logs record confidential data.** Uvicorn's access log prints every path and query string (workspace IDs, search terms such as provider names) to the container log. | `docker logs` output during the Part C smoke test. | ✅ `roi serve` runs with `access_log=False`, `server_header=False` (opt-in `--access-log`) |
| B-21 | Medium | TPR | **No notice-deadline view.** The date by which notice must be given (end date − notice period) is what drives exit and renegotiation planning, and it is not shown anywhere. | Only "critical arrangements expiring within 365 days" in the CRO report. | ✅ `analytics/renewals.py` notice schedule, *Renewals* page (critical filter), key message for critical deadlines within 90 days |
| B-22 | Low | TPR | Accepted findings and their justifications are missing from the Markdown/HTML validation reports (only JSON has them). | Rendered report. | ✅ accepted findings section in Markdown and HTML reports |
| B-23 | Low | TPR | Failure-impact table does not show whether each affected service has an exit plan. | Provider page. | ✅ exit-plan column in the failure-impact table |
| B-24 | Low | SE | An acceptance whose record is later edited (key changes) stays in the store as an orphan. | Code inspection. | ✅ acceptances whose finding disappeared are pruned with an audit entry |

## Cycle 3

| ID | Sev. | View | Finding | Evidence | Status |
|---|---|---|---|---|---|
| B-25 | Medium | TPR | **CRO report still counts only direct dependencies** – chart, table and tooltips contradict the key message and the provider pages after B-03, and pure fourth parties never appear. | `build_charts` used `critical_functions`; Nimbus group shown with 14 instead of 16. | ✅ chart and table show functions depending on each group including subcontracting (direct count alongside); pure subcontractors included |
| B-26 | Low | SE | README screenshots predate the Renewals/Audit tabs and the failure-impact table. | Visual check. | ⏳ regenerated with the release (hardening) |
| B-27 | Low | SE | `docs/ARCHITECTURE.md` did not list the new modules (impact, renewals, limits, security). | Doc review. | ✅ |
| B-15 | Low | SE | (cycle 1) Language switch dropped the query string. | — | ✅ `lang_href` keeps all parameters |

Re-review after the fixes (both perspectives, same probes as cycles 1–3: cross-session access,
cross-origin POST, open redirect, oversized/bomb archives, formula injection, rule crash,
direct vs indirect dependency figures in app/report/key messages, diff noise) found **no
remaining High or Medium items**. Open Low items: B-16 (findings export to spreadsheet),
B-17 (validator messages EN only), B-26 (screenshots, scheduled with the release).
