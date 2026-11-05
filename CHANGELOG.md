# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0.0, minor versions may
contain breaking changes to the Python API, the JSON report schema or the project-file
format; they are listed under **Changed** with migration notes.

## [Unreleased]

### Added

**DORA programme modules** (on the same register, in the workbench and the CLI, EN/DE)
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

[Unreleased]: https://github.com/crayfisher92/dora-roi-toolkit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/crayfisher92/dora-roi-toolkit/releases/tag/v0.1.0
