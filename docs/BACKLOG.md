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

---

# DORA programme modules (branch `contracts-incidents`)

Review of the Art. 30 contract gap analysis, incident classification, FINMA mapping and
readiness dashboard, with the same two perspectives and severity scale as above, after
merging the hardening work of the base branch. IDs `P-xx`.

## Programme cycle 1

| ID | Sev. | View | Finding | Evidence | Status |
|---|---|---|---|---|---|
| P-01 | High | SE | **Programme data is not saved in project files.** Art. 30 assessments and the incident log are lost when a workspace is saved as `.roiproj` and reopened (and on every autosave restart). | `save_project` → `load_project` of the sample: 13 assessments / 5 incidents → 0 / 0. | ✅ optional `programme` table in `.roiproj` (D-068); round-trip, legacy-file and tamper tests |
| P-02 | High | SE | **Assessment and incident changes do not trigger autosave and are missing from the audit trail.** Only register edits call `on_change` and append a `Change`. | `ws.contracts.save(...)` → 0 `on_change` calls; audit CSV has no programme entries. | ✅ `Workspace.programme_changed` → audit trail (kinds `art30`/`incident`) + autosave; shown on the audit page and in the CSV (D-069) |
| P-03 | Medium | SE | **Programme mutations are not serialised** by the workspace lock introduced in B-09; two concurrent saves of the same assessment can interleave history entries. | Code inspection (`contracts_routes`, `incidents_routes`). | ✅ all programme mutations under `ws.lock`; 8-thread test |
| P-04 | Medium | SE | **Art. 30 portfolio recomputed several times per request**: ~1.2 s each on a 10 000-contract register (contracts page: twice; overview: readiness + FINMA). | Timing with `sample.large.generate_large()`. | ✅ portfolio cached on the workspace, invalidated on edits/programme changes (D-070) |
| P-05 | Medium | SE | **Incident timestamps are not validated.** Occurrence after awareness, classification before awareness or resolution before the start are accepted and silently produce wrong durations and deadlines. | Incident with classified_at = detected − 1 d → initial notification due in the past; duration 0 h. | ✅ chronology validator on `Incident`; field-specific form errors; report submissions checked |
| P-06 | Medium | TPR | **No risk acceptance for contract gaps.** Hyperscalers rarely grant unrestricted audit rights; banks accept the residual risk with compensating controls. Such gaps stay open forever and keep the contracts pillar red. | No field or action for it; base B-12 only covers validation findings. | ✅ time-bound exceptions (reason, approver, end date) – status *Gaps under exception*, *Approved exceptions* in plan/Excel, expiry → open gap (D-071) |
| P-07 | Medium | TPR | **Concentration pillar is red because of contract expiries and notice deadlines** (contract lifecycle, not concentration), and its actions are the English key-message titles even in the German report. | Sample: concentration red from "5 arrangements expire …" / "2 notice deadlines …"; DE report shows English text. | ✅ concentration light from concentration metrics; expiries, notice deadlines and "renegotiate before notice deadline" in the contracts pillar; translated actions (D-072) |
| P-08 | Medium | TPR | **Readiness report has no PDF, and its print layout breaks in WeasyPrint** (pills stretch across the page, one card per row → 8 pages), although the base now produces PDFs for the other reports. | `html_to_pdf(render_readiness_html(...))`, page images. | ✅ PDF downloads/CLI `.pdf` via WeasyPrint; print CSS without `min()` grid tracks and inline flex (6 instead of 8 pages) |
| P-09 | Low | SE | Programme reports (plan, incident summary, readiness) are served with the app CSP instead of the stricter report CSP. | Response header of `/contracts/plan.html`. | ✅ report CSP for plan, incident summary and readiness report |
| P-10 | Low | TPR | Suggestion snippets cross clause boundaries (an audit match in clause 12 shows the end of clause 11). | Screenshot 12-assessment. | ✅ snippet clipped to the matched clause |
| P-11 | Low | TPR | No consistency hints between register and assessment (e.g. notice periods reported in B_02.02 while the termination clause is assessed missing; exit plan = true but no exit clause). | Inspection. | ✅ consistency hints on the assessment page (notice periods, locations, subcontractors, exit plan, audit date) |
| P-12 | Low | TPR | Possible recurring incidents without a recurrence key are not pointed out (same provider and root-cause category within six months). | Inspection. | ✅ *Possible recurring incidents* (same provider and root-cause category within 6 months, no common key) |

## Programme cycle 2

| ID | Sev. | View | Finding | Evidence | Status |
|---|---|---|---|---|---|
| P-13 | Medium | SE | **A malformed .docx crashes the request** (HTTP 500): a member whose declared size or CRC does not match raises `BadZipFile`, which the extractor does not catch; members that lie about their size are not covered by a ratio guard. | Crafted docx with patched size headers → uncaught `BadZipFile: Bad CRC-32`. | ✅ `zipfile`/`zlib` errors → *corrupt .docx file* (400); members read through a bounded stream; ratio guard as in `io.limits` |
| P-14 | Medium | TPR | **Importing assessments or an incident log discards history.** An imported entry with the same key replaces the existing one including its history (who decided what, when). | Book with 2 history entries + import of the same ref → 1 entry left. | ✅ imports merge histories (duplicates dropped, time order) and append an *imported* entry; the page reports new vs updated |
| P-15 | Medium | TPR | **"One dataset" is not possible for a Swiss group:** the Swiss bank's own arrangements cannot be kept in the register without flowing into the DORA xBRL-CSV submission – there is no way to mark entities as outside the DORA scope and leave them (and arrangements used only by them) out of the supervisory package. | FIN-OS-04 note; export uses the whole register. | ✅ DORA reporting scope on the FINMA page and `roi export --exclude-entity`; the xBRL-CSV package is built from the register restricted to the scope (`dora_roi.scope`), saved in project files and audited (D-073) |
| P-16 | Medium | TPR | **No remediation progress.** The plan lists gaps, but not whether negotiation has started or a clause is agreed and awaiting signature – the question the board asks about the 18 high-priority gaps. | Only the client-status column of the Excel export, which cannot be read back. | ✅ progress (planned / in negotiation / agreed), owner and agreed target date per gap – form, re-importable workbook, plan (HTML/PDF/Excel), contracts page, readiness line and *overdue* action (D-074) |
| P-17 | Low | TPR | The incident page does not show the contractual leverage with the affected provider (incident assistance Art. 30(2)(f), reporting obligations Art. 30(3)(b)). | Inspection. | ✅ *Contractual support (Art. 30)* panel on the incident page: 30(2)(f) and 30(3)(b) for the linked arrangements (D-075) |
| P-18 | Low | SE | The assessment form (22 fieldsets, ~150 controls) has no in-page navigation; keyboard and screen-reader users must tab through everything to reach one provision. | Keyboard walk-through. | ✅ provision index (links with status) at the top of the assessment form; each fieldset is a link target |
| P-19 | Low | TPR | Incidents affecting several entities are classified once on combined answers; per-entity classification and aggregated group reporting are not modelled. | Inspection. | ➖ documented (A-INC-08, D-076) and stated on the incident form; conservative by construction |
