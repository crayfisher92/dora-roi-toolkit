# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions may
contain breaking changes to the Python API, the JSON report schema or the project-file
format; they are listed under **Changed** with migration notes.

## [Unreleased]

### Fixed

- Release workflow: the GitHub release job downloads only the wheel/sdist and the release
  notes (it failed on unrelated CI artifacts for v0.2.0-rc.1), and the install line in the
  release notes names the actual wheel file.

## [0.2.0-rc.1] - 2026-11-15

Release candidate for the pilot ([`docs/PILOT.md`](docs/PILOT.md)): team use of the
workbench ([`docs/TEAM_DEPLOYMENT.md`](docs/TEAM_DEPLOYMENT.md)), the reconciliation of the
register with the official EBA material for reporting framework 4.0, the DORA programme
modules (experimental), an opt-in GLEIF check and a security self-test in CI.

### Added – pilot readiness

- **Opt-in online LEI check against GLEIF** (`roi validate --online`; in the workbench
  *Check LEIs with GLEIF* on the Fix page when `ROI_GLEIF=1`): unknown LEIs (`GLEIF-001`),
  lapsed, retired or annulled LEIs and inactive entities with their successor (`GLEIF-002`),
  names (`GLEIF-003`) and countries (`GLEIF-004`) that differ from the GLEIF record. Sends
  only the LEIs to `api.gleif.org`; off by default, the toolkit stays offline otherwise.
- **Security self-test in CI** on the built container: `scripts/security_selftest.py`
  (headers, cookies, CSRF, path traversal, size limits, API surface, team-mode header
  spoofing), an OWASP ZAP baseline scan, and the **sign-in end to end through oauth2-proxy
  with a mock Entra ID** (`scripts/sso_check.py`, `deploy/team/compose.ci-mock.yml`).
  Scope for the external penetration test in
  [`docs/SECURITY_TESTING.md`](docs/SECURITY_TESTING.md).
- **Entra ID sign-in test protocol** for the client's tenant
  ([`docs/ENTRA_SIGNIN_TEST.md`](docs/ENTRA_SIGNIN_TEST.md)) and a pilot plan with success and
  exit criteria ([`docs/PILOT.md`](docs/PILOT.md)); *Pilot feedback* issue template.
- In team mode the header shows the signed-in user and a *Sign out* link.

### Security

- Cookies carry the `Secure` flag in team mode (the TLS proxy made the app see HTTP, so the
  session cookie never had it) or with `ROI_SECURE_COOKIES=1`; all cookies are `HttpOnly`.
- The interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are switched off.
- The team deployment uses oauth2-proxy **v7.15.6** (was v7.7.1) with the `entra-id`
  provider, PKCE, `SameSite=Lax` and an 8-hour session.

### Added – engineering

- **Locked dependencies:** hash-pinned, universal locks in `requirements/` (`scripts/lock.sh`,
  `make lock` / `make lock-upgrade`); CI, `make install` and the Docker image install exactly
  them; CI fails when they drift from `pyproject.toml`; pip-audit scans the locked runtime set.
- **GitHub Actions pinned to commit SHAs**, kept current by Dependabot (actions and the Docker
  base image).
- **The release runs the complete CI workflow on the tag** (`ci.yml` is reusable), so releases
  pass exactly the checks of every pull request, including browser, scale and Docker tests.
- **Fuzz tests** of the parsers for untrusted files (`tests/test_fuzz.py`, Hypothesis): xlsx,
  CSV zips, xBRL-CSV packages, project files (bytes and tampered content) and inventories –
  25 examples each in CI, 1 500 in the weekly `fuzz` workflow.

### Changed – engineering

- **The web app is split into routers** (`dora_roi.web.routes`: home, wizard, workspace,
  analysis, export) sharing a `WebContext`; `app.py` only wires them together.
- **`dora_roi.workspace` is a package:** `core` (the workspace), `history` (audit trail and
  undo), `derived` (parsing, validation, acceptances) and `session` – the web-app state
  (owner, project file, edit lock) now lives in `Workspace.session` instead of on the
  workspace itself.
- **Clear error contracts for untrusted files** (found by fuzzing): `load_raw` raises only
  `UnsupportedInputError` / `InputTooLargeError` (and `FileNotFoundError`), `read_inventory`
  only `InventoryError` / `InputTooLargeError`, `load_project` only `ProjectError` – corrupt
  workbooks, archives, CSV and tampered project files previously surfaced as crashes in the
  CLI. The CLI reports oversized input as an error message.

### Added – team use of the workbench

- **Sign-in through an SSO proxy** (`ROI_AUTH_HEADER`, `ROI_TRUSTED_PROXIES`, `roi serve
  --auth-header/--trusted-proxy`): the user comes from the proxy's header, accepted only from
  the proxy's address (401 without a sign-in, 403 around the proxy); workspaces belong to the
  user across browsers and the audit trail records the signed-in user. Example deployment
  with oauth2-proxy and Microsoft Entra ID in `deploy/team/`.
- **Private and team project spaces** in the projects folder (`users/<user>/`, `team/`),
  *Move to team space* and *Close and release* on the overview.
- **Edit locks:** one editor per project file; others get a read-only view; idle locks can be
  taken over after `ROI_LOCK_MINUTES` (30). Autosave never overwrites a file that changed on
  disk since it was read – it writes a conflict copy and tells the user.
- **Per-user memory share** (`ROI_MAX_USER_WORKSPACES`, `ROI_MAX_USER_ROWS`) on top of the
  global budget; `ROI_MAX_WORKSPACES` makes the global count configurable.
- **No blocking:** parsing, validation, project loading and saving run in worker threads
  (`ROI_MAX_PARALLEL_JOBS`, 4).
- **Request-size limit:** bodies above 26 MB are refused before they are read.

### Fixed

- The "validation incomplete" banner of a workspace was rendered inside the page title and
  never shown.
- The Docker image now has a `/data` folder owned by the app user, so a projects volume is
  writable.

### Reconciliation with the official EBA material

Reconciliation of the register data model, code lists and xBRL-CSV export with the official
EBA material for reporting framework 4.0 (`reference/eba/`, see
[`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md#reconciliation-status)).

### Added

- `reference/eba/`: the official EBA files (annotated table layout, list of possible values,
  technical checks and validation rules, licensed activities, DORA xBRL-CSV sample instance,
  RoI reporting FAQ, data model) with provenance and checksums.
- `dora_roi.model.eba_codes`: the taxonomy member of every code-list value, the B_06.01
  licensed activities and the DPM country/currency lists; `scripts/gen_eba_codes.py`
  regenerates the tables from `reference/eba/`.
- Template **B_99.01** (definitions from entities making use of the ICT services, DPM 4.0):
  one optional row with the entity's internal definition of each option of six closed
  lists (FAQ Q67); imported, validated (FLD-011: at most one row), exported and filled in the
  synthetic sample. Inputs without a B_99.01 sheet raise no IMP-002 warning.
- **Framework version by reference date** (`FRAMEWORK_VERSIONS`, `framework_for`): the DORA
  module of framework 4.0 for reference dates up to 31 December 2026; the xBRL-CSV export
  warns from December 2027, when the EBA plans DORA DPM/taxonomy amendments (framework 4.4
  phase 2). Sources in `reference/eba/README.md`.
- Code list `AlternativesIdentified` (B_07.01 c0110: yes / no / assessment not performed);
  `Impact.NOT_ASSESSED`; `NonSubstitutabilityReason.NOT_APPLICABLE`; entity types
  `OTHER_FINANCIAL` and `NON_FINANCIAL_ICT_INTRAGROUP`; provider code types CRN, VAT, PNR, NIN.
- **Mapping to the official EBA checks** (`dora_roi.validation.eba_mapping`): every rule lists the
  technical checks, DPM validation rules and GLEIF/BRIS checks it implements; `docs/REGULATORY_MAPPING.md`
  has an *EBA check* column and a coverage table of all 120 official checks; `roi rules -f json`
  includes `eba_checks`. A test fails if an active official check is neither implemented nor
  explained.
- Rule **FLD-015**: licensed activity outside the EBA list (ITS Annex IV) and currencies outside the
  DPM 4.0 currency list (EBA check 503).
- Tests against the official files: column codes and primary keys of every template
  (`tests/test_eba_reference.py`) and our package against the official sample instance.

### Changed

- **xBRL-CSV export** – every template is reported (empty ones as header-only files, plus
  B_99.01, now with its data) and every filing indicator is `true` (EBA technical check 808); all enumerations are
  exported as taxonomy members by default (`--code-map` now only overrides values); booleans
  that the DPM models as enumerations are exported as such; the ESAs' conventions for empty key
  fields are applied ("Not Applicable", `eba_GA:qx2007`, own LEI as parent, own code as rank-1
  recipient); licensed activities are exported as `eba_TA:` members; warnings for values
  outside the DPM country/currency lists; `--level` accepts only `CON` and `IND`; the
  non-standard `x-dora-roi-toolkit` member was removed from `report.json`.
- **Templates** – B_03.03 "Link" is `c0031` (was `c0030`); B_03.02 has no "Link" column
  (was `c0040`) – old workbooks still import; the B_02.02 key includes c0130, c0150 and c0160;
  B_02.02 c0130 is conditional; B_07.01 c0110 is a code list instead of a boolean.
- **Code lists** – `HierarchyInGroup.OTHER` is now `OUTSOURCING` (old code still accepted);
  `EntityType.REINSURANCE_UNDERTAKING` merged into `INSURANCE_UNDERTAKING` (old code still
  accepted); `EntityType.OTHER` means a non-financial entity other than an ICT intra-group
  service provider; `AdditionalCodeType` lost BIC and OTHER and gained LEI and EUID.
- **Validation** – BUS-010 accepts an entity's own LEI as parent when it has no direct parent
  (FAQ Q58); SC-004 accepts the provider itself as rank-1 recipient (FAQ Q65); FLD-013 applies
  the EUID format only to EUIDs and now also checks the additional provider code (B_05.01
  c0030/c0040). "Not Applicable", an own LEI as parent and an own code as
  rank-1 recipient are read as empty values on import.
- **BUS-002 / BUS-003** follow FAQ Q52–53 (only arrangements in force are reported):
  BUS-002 is now a warning for an arrangement that ended before the reference date (an end
  date on the reference date is still in force) instead of an error for a missing
  termination reason; BUS-003 warns about any termination reason in B_02.02 c0090. The
  clean sample no longer contains ended arrangements, so the sample with injected errors
  reports 25 errors and 6 warnings (was 27 and 5).
- **Requirement levels** follow the ITS reporting instructions (see A-TPL-10): B_02.02 c0100,
  c0110, c0120, c0140 and c0180 are mandatory only for ICT services supporting a critical or
  important function; total assets (B_01.02 c0110) only for financial entities; the
  provider's total annual expense (B_05.01 c0100) only for direct providers; the deletion
  date (B_01.02 c0090), the provider name in Latin alphabet (B_05.01 c0060), RTO/RPO (B_06.01
  c0080/c0090) and the audit date (B_07.01 c0070) are mandatory, with the ITS values
  9999-12-31 and 0 for "none" / "not defined" offered as fix suggestions; reasons for
  criticality (B_06.01 c0060) and named alternatives (B_07.01 c0120) are optional. New rule
  **FLD-014** checks the conditional columns; BUS-015 and BUS-021 are warnings; BUS-005 applies
  to critical services only; 9999-12-31 counts as "no audit" in BUS-022 and is ignored by
  BUS-012.
- Country `XK` (Kosovo) is accepted, as in the EBA list.
- `roi check-package` reports a different column order as a warning, not a failure.
- The synthetic sample uses the EBA labels for licensed activities.

### Added – DORA programme modules (experimental, under regulatory review)

On the same register, in the workbench and the CLI, EN/DE. The review against the source
texts and its fixes are listed in [`docs/MODULE_REVIEW.md`](docs/MODULE_REVIEW.md).

- **Art. 30 contract gap analysis**: 22-item checklist with article references
  (`roi contracts checklist`); present / partial / missing per provision with clause
  reference and evidence, linked to B_02.01 (status on register rows and provider pages);
  inheritance from overarching arrangements; portfolio by criticality; prioritised
  remediation plan as HTML, PDF, Excel and JSON with progress (planned / in negotiation /
  agreed), owners, agreed or proposed target dates and approved time-bound exceptions;
  re-importable assessment workbook; local keyword suggestions from PDF/DOCX/TXT contracts
  (no network, clearly marked as suggestions); register ↔ contract consistency hints.
- **Major ICT incident classification**: guided questionnaire on the RTS criteria with
  unknown answers, triggered thresholds, initial / intermediate / final reporting deadlines
  with live countdown, incident log with history, recurring incidents, links to providers,
  arrangements and functions, contractual support (Art. 30(2)(f), (3)(b)) per incident,
  summary as HTML, PDF and JSON (`roi incidents criteria|summary`).
- **Switzerland (FINMA)**: RoI fields, Art. 30 items and the incident log mapped to FINMA
  Circ. 2018/3 and 2023/1 with coverage by design and in the register (`roi finma`); a
  **DORA reporting scope** so a Swiss group keeps one dataset – entities outside the scope
  are left out of the xBRL-CSV package (`roi export --exclude-entity`), which is validated
  as such.
- **DORA readiness dashboard** per client and CRO report (HTML/PDF, `roi readiness`):
  register, contracts, incidents, concentration and FINMA as traffic lights with priority
  actions.
- Programme data in project files and in the audit trail (changes and exports); Alpenrand
  sample assessments, contract document and incidents (`roi sample --assessments
  --incidents --contract-document`); 10-minute demo in `docs/DEMO.md`.

### Changed – review of the programme modules against the source texts

Details, sources and open items in [`docs/MODULE_REVIEW.md`](docs/MODULE_REVIEW.md); the
modules carry an *Experimental* notice in the workbench.

- **Art. 30**: keyword suggestions never count as present – `roi contracts suggest` writes
  every status as *not assessed* with the proposal in `suggested_status`; "Compliant" is now
  "All checklist items present". Item texts corrected for 30.2.d, 30.2.h (Art. 28(7) is a
  separate obligation), 30.3.a, 30.3.e.i (copies only where critical to the provider;
  microenterprise delegation) and 30.3.e.ii (certifications alone are no evidence, RTS
  2024/1773 Art. 8(3)); invented transition period removed; RTS 2025/532 cited as final.
- **Incidents**: a classification made more than 24 h after awareness is due 4 h later
  (RTS 2025/301 Art. 5(2)); a missing classification time no longer makes the deadline move
  with the clock; a malicious access meets the critical-services criterion (RTS 2024/1772
  Art. 6(c)); "overdue" now reads "past the conservative deadline".
- **FINMA**: margin numbers cited and checked; FIN-OS-02/03/04/14 partly instead of fully
  covered, FIN-OR-02 not covered (an RTO is no tolerance for disruption). The sample now
  scores 44 % instead of 56 %.
- **Readiness**: renamed "DORA readiness – third parties and incidents" with a scope note;
  "ready for submission" now "no blocking errors in the toolkit's validation"; Switzerland
  counts as a third country in the DORA view; notice periods measured from today.
- `.docx` extraction refuses a DTD anywhere in the part, not only in the first 4 KiB.

### Reconciliation (continued)


## [0.1.0] - 2026-11-05

First public release: a working toolkit for preparing, checking and analysing a DORA Register
of Information (Regulation (EU) 2022/2554, ITS on the register templates). **Not an official
EBA/ESA tool and not legal advice** – the template structure and rules have not yet been
reconciled against the official EBA taxonomy package (see [Known limitations](#known-limitations)).

### Added

**Data model and validation**
- Typed Pydantic model for all 14 templates B_01.01 – B_07.01 with ITS column codes, labels,
  mandatory / conditional / optional levels and code lists (ICT service types, criticality,
  substitutability, reliance, data sensitivity, …) that also accept labels and aliases.
- Validation engine with 63 rules in four families – field (mandatory, LEI checksum, ISO
  dates / countries / currencies, code lists, duplicates), referential (cross-template keys),
  supply chain (ranks, recipients, cycles) and business (exit plans, notice periods, critical
  functions, duplicate providers) – each mapped to DORA articles and ITS provisions
  ([`docs/REGULATORY_MAPPING.md`](docs/REGULATORY_MAPPING.md)).
- Reports as text, Markdown, HTML, JSON, **PDF** and an Excel findings list for business
  owners (explanation, regulation, owner/status columns); configurable severities
  (`--disable`, `--downgrade`), exit codes for CI pipelines.

**Import and export**
- Excel workbook import/export (tolerant sheet and header recognition, drop-down code lists),
  CSV folder / zip, best-effort xBRL-CSV package export and import, `roi check-package` against
  a reference package, blank template generation.
- Column-mapping wizard for messy client inventories (German or English headers, local date
  and number formats, country names, yes/no flags).
- **Project files** (`.roiproj`, SQLite): raw values, full change history, versions and
  accepted findings in one portable file; optional autosaving projects folder.

**Analytics and reporting**
- Concentration analytics by ultimate parent group (HHI, top shares), critical-function
  dependencies including subcontracting chains, provider failure impact, geographic and data
  location concentration, substitutability and exit-plan coverage, notice-deadline schedule.
- CRO executive summary (HTML/PDF) with accessible SVG charts and key messages; register diff
  separating material from administrative changes.

**Workbench (web UI)**
- Guided Import → Fix → Analyse → Export flow with a quality score and readiness status.
- Inline fixing with explanations, regulation references, suggestions and bulk replace;
  accepting warnings with a justification; full audit trail (who, when, old → new, and every
  export) exportable as CSV (`roi audit-log`); versions and comparison with a previous register.
- Browsable register, provider pages with failure impact and exit plans, interactive
  dependency graph, renewals page.
- English and German, WCAG 2.2 AA (axe-core in CI), keyboard operable, responsive,
  light/dark themes, print-friendly pages.

**Security and operations**
- Threat model ([`docs/SECURITY.md`](docs/SECURITY.md)) and disclosure policy
  ([`SECURITY.md`](SECURITY.md)); strict CSP and security headers, same-origin checks against
  CSRF, per-browser session isolation, upload / archive / row limits, formula-injection-safe
  Excel output, XXE-safe spreadsheet reading, offline PDF rendering, no access log or telemetry.
- Hardened Docker image (non-root, read-only root filesystem, no capabilities) and
  `docker-compose.yml`; CI with ruff, mypy (strict), pytest (≥ 85 % coverage on 3.11–3.13),
  Playwright end-to-end and accessibility tests, bandit, pip-audit, Docker smoke test and a
  10 000-contract scale test ([`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)).
- Release workflow building the wheel, sdist and multi-architecture Docker image from a
  version tag.

### Known limitations

- Template columns, code-list members and rule identifiers are derived from the published ITS
  and have **not yet been reconciled** with the official EBA "Annotated Table Layout" and
  xBRL-CSV sample package; xBRL-CSV export is therefore best-effort and must be checked with
  the authority's validation before filing ([`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md)).
- The workbench has no user accounts; shared deployments need an authenticating reverse
  proxy. Project files are not encrypted.

[Unreleased]: https://github.com/crayfisher92/dora-roi-toolkit/compare/v0.2.0-rc.1...HEAD
[0.2.0-rc.1]: https://github.com/crayfisher92/dora-roi-toolkit/compare/v0.1.0...v0.2.0-rc.1
[0.1.0]: https://github.com/crayfisher92/dora-roi-toolkit/releases/tag/v0.1.0
