# Architecture

```
                 ┌──────────── importers (dora_roi.io) ────────────┐
 .xlsx ─────────▶│ excel.read_workbook                              │
 CSV folder/zip ▶│ csv_folder.read_csv_folder / read_csv_files      │──▶ RawRegister ──▶ parse.parse_raw ──┐
 xBRL-CSV pkg ──▶│ xbrl_csv.read_xbrl_csv                           │   (column code → raw   (Pydantic, FLD-*  │
                 └──────────────────────────────────────────────────┘    value + row no.)     findings)       │
                                                                                                             ▼
                                         ┌───────────────── RegisterOfInformation (dora_roi.model) ────────────────┐
                                         │ 14 typed template models, column metadata (Col), code lists, look-ups  │
                                         └───────┬───────────────────────┬────────────────────────┬────────────────┘
                                                 ▼                       ▼                        ▼
                                  validation.validate          analytics.analyse         exporters (excel, csv,
                                  (XRF/SC/BUS/FLD rules)       (ConcentrationAnalysis)    xbrl_csv best effort)
                                                 │                       │
                                                 ▼                       ▼
                                  ValidationReport ──▶ reporting: JSON / Markdown / HTML · executive summary HTML
                                                 └───────────────┬───────┘
                                                                 ▼
                                                     cli (roi …)   ·   web (FastAPI)
```

### DORA programme modules

```
                    RegisterOfInformation (source of truth for providers, entities, functions)
                                │ joined by key at evaluation time, never copied (D-049)
        ┌───────────────────────┼─────────────────────────────┬─────────────────────────┐
        ▼                       ▼                             ▼                         ▼
 AssessmentBook          IncidentLog                   FINMA requirements        ConcentrationAnalysis
 (B_02.01 c0010 →        (answers, timestamps,         (RoI columns, Art. 30     (analytics, unchanged)
  22 Art. 30 items)       provider/contract/entity      items, incident log)
        │                 links, history)                      │
 contracts.analysis      incidents.classify ·                  │
 → Portfolio →           deadlines · recurring                 │
   RemediationPlan       → IncidentOverview                    │
        └───────────────────────┴──────────────┬──────────────┘
                                               ▼
                         readiness.build_readiness → ReadinessView (traffic lights, actions)
                                               ▼
              Workbench screens (contracts, incidents, FINMA, dashboard) · CLI · HTML/Excel/JSON
```

Assessments and incidents are workspace state (in memory, D-054) with their own JSON formats;
outcomes (compliance status, classification, deadlines, coverage, traffic lights) are always
*derived* from them and the register, never stored (D-057).

## Packages

| Package / module | Responsibility |
|---|---|
| `dora_roi.model` | `templates.py` – one Pydantic model per template (B_01.01 … B_07.01) with `Annotated[..., Col(code, label, requirement, kind, codelist)]` fields; `codelists.py` – `CodeEnum` code lists with label/alias lookup; `types.py` – annotated format types (LEI, country, currency, ISO date, boolean, amount); `refdata.py` – ISO 3166 / ISO 4217 / EU / EEA data; `register.py` – `RegisterOfInformation` container and cross-template indexes. |
| `dora_roi.lei` | ISO 17442 LEI syntax and MOD 97-10 check digits. |
| `dora_roi.io` | `raw.py` – untyped `RawRegister`; `tables.py` – sheet/file name recognition, header detection, annotation-row skipping; `excel.py` (XlsxWriter), `xlsx_read.py` (python-calamine), `csv_folder.py`, `xbrl_csv.py` – readers and writers; `limits.py` – size and row limits; `parse.py` – raw → typed with field findings; `loader.py` – format detection, `load()` / `save()`. |
| `dora_roi.validation` | `findings.py` – `Finding`, `Severity`, `Rule` and the rule registry/decorator; `context.py` – `ValidationConfig` and cached indexes; `field_rules.py`, `referential_rules.py`, `supply_chain_rules.py`, `business_rules.py` – the rules; `engine.py` – `validate()` and `ValidationReport`; `references.py` – regulatory reference labels. |
| `dora_roi.analytics` | `concentration.py` – provider/group exposure, HHI, critical-function dependencies, geography, subcontracting, substitutability, expiries, key messages. |
| `dora_roi.reporting` | Validation report renderers, executive summary, inline SVG charts, Jinja2 templates and shared CSS (light/dark, print/A4); `pdf.py` renders the print variant to PDF with WeasyPrint (optional, offline). |
| `dora_roi.sample` | Fictional *Alpenrand* group catalogue and deterministic generator with injected errors; `large.py` – scale-test register (10 000 contracts / 1 000 providers by default). |
| `dora_roi.cli` | `roi validate · report · export · template · rules · sample · serve`. |
| `dora_roi.workspace` | Editable, versioned register (raw values as source of truth, instant re-validation). |
| `dora_roi.fixes` / `dora_roi.explain` / `dora_roi.quality` | Fix suggestions and bulk groups; EN/DE plain-language rule explanations; data-quality score and readiness. |
| `dora_roi.inventory` / `dora_roi.normalise` | Column-mapping import of arbitrary inventories; value normalisation (countries, dates, amounts, booleans, service types). |
| `dora_roi.diff` / `dora_roi.graph` | Register comparison (material vs administrative changes); layered dependency graph with SVG rendering. |
| `dora_roi.analytics.impact` / `.renewals` | Failure impact of a provider (direct and through subcontracting); notice-deadline schedule. |
| `dora_roi.io.limits` | Upload/archive size, compression-ratio and row-count limits. |
| `dora_roi.web.security` | Security headers/CSP, same-origin (CSRF) check, browser-session isolation, safe redirects. |
| `dora_roi.web` | Workbench: FastAPI routes (`app.py`), view models (`views.py`), EN/DE strings (`i18n.py`), Jinja2 templates, `static/app.css` + `app.js` (progressive enhancement), `devserver.py` for tests/screenshots. |
| `dora_roi.contracts` | `provisions.py` – the 22-item Art. 30 checklist (EN/DE, article references, keyword concepts); `model.py` – `AssessmentBook`/`ContractAssessment` with history, time-bound exceptions and remediation progress, JSON and Excel I/O, history-preserving merge on import; `analysis.py` – register contexts, inheritance from overarching arrangements, `Portfolio`, `RemediationPlan` (priorities, progress, overdue), incident-related provisions; `consistency.py` – register ↔ assessment hints; `extract.py` – local PDF (pypdf)/DOCX/TXT text extraction; `suggest.py` – clause-aware keyword suggestions; `report.py` – remediation plan HTML/PDF/Excel. |
| `dora_roi.incidents` | `criteria.py` – criteria and `Thresholds`; `model.py` – `Incident`, `Answers`, `IncidentLog` (UTC, display time zone, history); `classify.py` – three-valued classification, recurring groups; `deadlines.py` – reporting timeline; `report.py` – views linked to the register, summary HTML/JSON/Markdown. |
| `dora_roi.finma` | FINMA Circ. 2018/3 and 2023/1 requirements mapped to RoI columns, Art. 30 items and the incident log; completeness over applicable records; Swiss context. |
| `dora_roi.scope` | DORA reporting scope of a group dataset: `restrict_to_scope` drops entities outside the DORA scope and what only concerns them before the xBRL-CSV package is built (web download, `roi export --exclude-entity`). |
| `dora_roi.readiness` | Traffic lights per pillar, priority actions, readiness report (print/PDF-friendly HTML). |
| `dora_roi.i18n` | EN/DE strings of the programme modules and their reports (merged into the web catalogue). |
| `dora_roi.web.*_routes` | Route modules for the programme screens, registered through the `Ui` context (`web/context.py`). |
| `dora_roi.docs` | Generates `REGULATORY_MAPPING.md`, `DATA_DICTIONARY.md`, `SAMPLE_DATA.md`, `ART30_CHECKLIST.md`, `INCIDENT_CLASSIFICATION.md` and `FINMA_MAPPING.md` from the code. |

## Key design choices

See [DECISIONS.md](DECISIONS.md). In short:

1. **Load everything, then judge.** Fields are `Optional`; format errors are recorded and the
   bad value dropped, so one run reports every problem (D-002, D-003, D-011).
2. **Single source of truth.** Column metadata lives on the model fields and drives the
   template generator, importers, exporters, validation and documentation (D-004, D-019).
3. **Rules are data.** Every rule carries ID, severity, category, templates, regulatory
   references and description; the regulatory mapping is generated from them.

## Adding a rule

```python
from dora_roi.validation.findings import Category, Severity, rule

@rule("BUS-100", "Notice period shorter than 30 days for critical services",
      severity=Severity.WARNING, category=Category.BUSINESS, templates=("B_02.02",),
      references=("DORA Art. 28(7)",),
      description="Short notice periods limit the entity's ability to exit in an orderly way.")
def check_short_notice(ctx):
    for s in ctx.critical_services:
        if s.notice_period_entity is not None and s.notice_period_entity < 30:
            yield ctx.finding("BUS-100", f"Notice period of {s.notice_period_entity} days", s,
                              "notice_period_entity")
```

Import the module from `dora_roi/validation/__init__.py`, add a firing case to
`tests/test_validation.py::CASES` (a test fails if any engine rule lacks one) and run
`python -m dora_roi.docs` to refresh the regulatory mapping (a test fails if it is stale).
New references must be added to `dora_roi/validation/references.py`.

## Validation report JSON schema (`dora-roi-toolkit/validation-report/v1`)

```jsonc
{
  "schema": "dora-roi-toolkit/validation-report/v1",
  "toolkit_version": "0.1.0",
  "generated_at": "2026-11-05T10:00:00+00:00",
  "source": "register.xlsx",
  "reference_date": "2025-12-31",
  "maintainer": {"lei": "…", "name": "…"},
  "passed": false,                         // no error-level findings and no rule crashes
  "summary": {
    "severity_counts": {"error": 3, "warning": 1, "info": 0},
    "rules_run": 62,
    "record_counts": {"B_01.01": 1, "...": 0},
    "by_template": {"B_02.02": {"error": 2, "warning": 0, "info": 0}},
    "by_rule": [{"rule_id": "FLD-005", "title": "…", "severity": "error", "count": 1}]
  },
  "findings": [{
    "rule_id": "FLD-005", "severity": "error", "category": "field",
    "message": "c0120 'Country of the governing law…': 'UK' is not an ISO 3166-1 alpha-2 country code (did you mean 'GB'?)",
    "template": "B_02.02", "row": 54, "column": "c0120",
    "record_key": "AR-DE-0012 | <LEI> | <provider> | F-DE-05 | S19",
    "value": "UK", "source": "register.xlsx:B_02.02"
  }],
  "rule_failures": []                      // rules that raised – never silently ignored
}
```

`row` is the 1-based row number in the source sheet/file; `column` the ITS column code.

## File formats of the programme modules

| Schema | Content | Produced / read by |
|---|---|---|
| `dora-roi-toolkit/contract-assessments/v1` | Assessments per arrangement: items (status, clause, evidence, suggested status, exception, remediation progress/owner/target date), assessor, date, document, notes, inheritance flag, history | `roi sample --assessments`, `roi contracts suggest -o`, workbench export/import |
| `dora-roi-toolkit/art30-remediation-plan/v1` | Status per arrangement and prioritised actions with target dates | `roi contracts assess -o plan.json` |
| `dora-roi-toolkit/incident-log/v1` | Incidents with answers, timestamps (UTC), links, report submissions, history; display time zone | `roi sample --incidents`, workbench export/import |
| `dora-roi-toolkit/incident-summary/v1` | Derived classification (criteria, triggers, open questions), deadlines with states, recurring series | `roi incidents summary -o .json`, workbench |
| `dora-roi-toolkit/finma-mapping/v1` | Coverage per FINMA requirement (by design, in the register), field fill rates, Swiss context | `roi finma -f json` |
| `dora-roi-toolkit/readiness/v1` | Traffic lights per pillar and priority actions | `roi readiness --json` |

The Excel assessment workbook (sheet `Assessments`: `contract_ref`, `provision_id`, `status`,
`clause_ref`, `evidence`, …) is the offline counterpart of the assessments JSON.

## Performance

All rules are linear or near-linear in the number of rows using pre-computed indexes
(`ValidationContext`). The ~1 000-row sample validates and is analysed in well under a second.
A register with 10 000 contracts and 1 000 providers (76 000 rows) imports in about 3 s,
validates in about 1 s and every workbench page renders in under 0.5 s – see
[`PERFORMANCE.md`](PERFORMANCE.md) and `scripts/profile_large.py` (also run in CI).
