# DORA RoI Toolkit

[![CI](https://github.com/crayfisher92/dora-roi-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/crayfisher92/dora-roi-toolkit/actions/workflows/ci.yml)

An open-source Python toolkit for the **DORA Register of Information (RoI)** under
Regulation (EU) 2022/2554 and the ESAs' Implementing Technical Standards on the register
templates (Commission Implementing Regulation (EU) 2024/2956).

It gives GRC consultants and ICT third-party risk teams:

- a **typed data model** of all 14 templates (B_01.01 – B_07.01) with column codes,
  mandatory/conditional flags, code lists and cross-template keys;
- a **validation engine** with 62 rules – field formats (LEI checksum per ISO 17442, ISO
  3166/4217/8601, code lists), cross-template referential integrity, subcontracting-chain
  resolution and DORA business rules (e.g. *critical functions have an exit plan*) – producing
  **HTML, Markdown and JSON** reports with severities and exact row/column locations;
- **import/export**: multi-sheet Excel (with a blank template generator), CSV folders/zips and
  a **best-effort xBRL-CSV** report package;
- **concentration-risk analytics** and an **executive summary** (HTML with charts) for a CRO;
- a **CLI** (`roi`) and the **DORA RoI Workbench** web app: guided *Import → Fix → Analyse →
  Export* workflow, column-mapping import of a client's own inventory, inline fixing with
  plain-language explanations, provider pages, an interactive dependency graph, register
  diff, English/German, WCAG 2.2 AA-tested;
- a realistic **synthetic dataset** for a fictional Swiss/EU banking group with deliberately
  injected errors.

> ⚠️ **Not an official EBA/ESA tool and not legal advice.** The toolkit was built from the
> structure of the regulation and the ITS; template details, code lists, validation rules and
> the xBRL-CSV package format are documented as assumptions in
> [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) and must be verified against the texts,
> taxonomy and filing rules in force before any supervisory use.

## Quickstart

**With Docker** (one command, no Python needed):

```bash
docker compose up --build          # → http://127.0.0.1:8000
```

**With Python:**

```bash
pip install -e ".[web]"            # Python ≥ 3.11; add [dev] for tests and linters
```

PDF reports additionally need `pip install -e ".[web,pdf]"` (WeasyPrint, which uses the Pango
library: preinstalled on most Linux desktops, `brew install pango` on macOS; on Windows use the
Docker image or print the HTML report to PDF – it has the same print layout).

```bash
roi sample alpenrand.xlsx          # synthetic register with 25 injected errors
```

```bash
roi validate alpenrand.xlsx        # human-readable summary; exit code 1 on errors
```

```bash
roi validate alpenrand.xlsx -f html -o validation.html
```

```bash
roi report alpenrand.xlsx -o executive-summary.html --client "Alpenrand Group"
```

```bash
roi report alpenrand.xlsx -o executive-summary.pdf --validation-report validation.pdf
```

```bash
roi export alpenrand.xlsx -o out/ --format xbrl-csv   # best-effort package (warns!)
```

```bash
roi template my-register.xlsx      # blank workbook with headers, hints and drop-downs
```

```bash
roi serve                          # web UI on http://127.0.0.1:8000
```

Pre-generated outputs for the sample live in [`examples/`](examples/):
[executive summary](examples/reports/executive-summary.html),
[validation report](examples/reports/validation-report.html) (also
[JSON](examples/reports/validation-report.json) and
[Markdown](examples/reports/validation-report.md)), the
[sample workbook](examples/alpenrand-sample.xlsx) and a
[blank template](examples/roi-blank-template.xlsx).

## The workbench (web UI)

```bash
roi serve          # or: docker compose up   →  http://127.0.0.1:8000
```

| | |
|---|---|
| ![Overview with stepper and data-quality score](docs/screenshots/02-overview.png) | ![Fix findings inline with suggestions](docs/screenshots/03-fix.png) |
| **Overview** – stepper, data-quality score, readiness, next best action | **Fix** – findings by template and severity, plain-language help, regulation, inline edit and bulk fix |
| ![Column-mapping wizard](docs/screenshots/07-mapping.png) | ![Dependency graph coloured by region](docs/screenshots/05-graph.png) |
| **Mapping wizard** – a client's own inventory, auto-suggested column mapping | **Dependency graph** – providers → subcontractors, by criticality or region |
| ![Provider page](docs/screenshots/06-provider.png) | ![Register diff](docs/screenshots/08-compare.png) |
| **Provider page** – risk flags, contracts, functions, chain | **Compare** – last year vs this year |

More: [register browser](docs/screenshots/04-register.png),
[German interface in dark mode](docs/screenshots/09-fix-dark-de.png). Personas, jobs and the
screen flow are in [`docs/UX.md`](docs/UX.md); a 5-minute client demo script is in
[`docs/DEMO.md`](docs/DEMO.md). Screenshots are regenerated with
`python scripts/make_screenshots.py`.

### CLI reference

| Command | Purpose | Notable options |
|---|---|---|
| `roi validate INPUT` | Validate a register | `-f text\|json\|md\|html\|pdf`, `-o FILE`, `--fail-on error\|warning\|never`, `--disable RULE`, `--downgrade RULE`, `--reference-date`, `--code-map` |
| `roi report INPUT -o FILE` | Executive summary (`.html` or `.pdf`) | `--client`, `--prepared-by`, `--validation-report FILE`, `--json FILE` |
| `roi export INPUT -o OUT` | Export | `--format xbrl-csv\|excel\|csv`, `--unzipped`, `--strict`, `--level CON\|IND\|SUB`, `--entry-point`, `--code-map` |
| `roi template FILE` | Blank Excel template | `--sample [--clean]` to pre-fill |
| `roi rules` | List rules and provisions | `-f text\|md\|json` |
| `roi sample OUT` | Generate the synthetic register | `--format xlsx\|csv`, `--clean`, `--previous-year`, `--inventory`, `--seed` |
| `roi diff OLD NEW` | Compare two registers | `-f md\|json`, `-o FILE` |
| `roi audit-log PROJECT` | Export the change history of a `.roiproj` project file as CSV | `-o FILE` |
| `roi check-package REF` | Compare our xBRL-CSV export with a reference (e.g. official sample) package | `--ours PKG`, `-o FILE` |
| `roi serve` | Start the web UI | `--host`, `--port`, `--projects DIR` (autosave project files), `--access-log` |

`INPUT` may be a `.roiproj` project file, an `.xlsx` workbook, a folder or `.zip` of CSV files (`b_02.02.csv` …), or an
xBRL-CSV package (zip or folder). Exit codes: `0` ok, `1` findings at/above `--fail-on`,
`2` usage/input error.

### Python API

```python
from dora_roi.api import validate_path
from dora_roi.analytics import analyse
from dora_roi.reporting import render_html
from dora_roi.reporting.executive import render_executive_summary

loaded, report = validate_path("register.xlsx")
print(report.severity_counts())            # {'error': 27, 'warning': 5, 'info': 1}
for f in report.errors[:3]:
    print(f.rule_id, f.location, f.message)

analysis = analyse(loaded.register)
print(analysis.top1_share, analysis.hhi_band, [k.title for k in analysis.key_findings])

open("validation.html", "w").write(render_html(report))
open("summary.html", "w").write(render_executive_summary(loaded.register, report))
```

The typed models can also be used directly:

```python
from dora_roi.model import ContractSpecific
row = ContractSpecific.model_validate({"contract_ref": "AR-1", "service_type": "SaaS",
                                       "governing_law_country": "DE"})
row.service_type          # <IctServiceType.S19: 'S19'>
```

## Workbook format

`roi template` produces one sheet per template named by its code (`B_02.02`). Row 1 holds the
ITS column codes, row 2 the labels (bold = mandatory), row 3 the requirement, format and
condition; data starts on row 4. Code-list columns have drop-downs and accept either the code
(`S19`) or the label (`Cloud services: SaaS`). The importer also accepts sheet-name variants
(`b0202`), label headers, title rows above the header, semicolon-separated CSV and UTF-8 BOMs.
See [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) for every column and code list.

## What gets checked

| Family | Rules | Examples |
|---|---:|---|
| Import (`IMP`) | 4 | unknown sheets, missing templates, unknown columns, no header |
| Field (`FLD`) | 13 | mandatory values, LEI checksum, ISO country/currency/date, code lists, numbers, duplicates, LEI-vs-EUID consistency |
| Referential (`XRF`) | 15 | every contract/entity/provider/function/branch reference resolves; contracts have services, signatories and users; overarching arrangements exist and are overarching |
| Supply chain (`SC`) | 6 | rank 1 is the direct provider, recipients resolve to the previous rank, no cycles, critical services have a chain |
| Business (`BUS`) | 24 | end ≥ start, termination reasons, data locations, critical-function RTO/RPO, assessments and **exit plans for critical functions**, substitutability reasons, audit recency, intra-group consistency |

The full list with the DORA article / ITS provision each rule supports is in
**[`docs/REGULATORY_MAPPING.md`](docs/REGULATORY_MAPPING.md)** (generated from the code).

## Concentration analytics

`roi report` / `dora_roi.analytics.analyse` compute, on the register as reported:

- spend share and **HHI by provider group** (ultimate parent, so a hyperscaler's EU and US
  entities count as one exposure) and the groups supporting many **critical or important
  functions**;
- for each critical function: providers, single-provider dependency, substitutability, exit
  plan coverage, subcontracting depth, data regions;
- **geographic concentration** by provider HQ and by ultimate parent HQ (EU / EEA / Switzerland /
  third country), service-provision and data-storage countries;
- **subcontracting depth** and **fourth-party ("hidden") concentration** – subcontractors that
  recur across many chains;
- substitutability mix, exit-plan coverage and arrangements supporting critical functions
  that expire within 12 months;
- plain-language **key messages** ranked high/medium/low (thresholds configurable via
  `AnalyticsConfig`).

## Architecture

```
importers (Excel · CSV · xBRL-CSV) → RawRegister → parser (format checks) → RegisterOfInformation
      → validation engine → ValidationReport ─┐
      → analytics → ConcentrationAnalysis ────┴→ reports (JSON · MD · HTML · executive) → CLI · web
```

Details, the JSON report schema and how to add a rule: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Configuration

| Environment variable | Default | Effect |
|---|---|---|
| `ROI_PROJECTS_DIR` | – | Folder for autosaved project files (same as `roi serve --projects`) |
| `ROI_MAX_UNCOMPRESSED_MB` | `200` | Maximum uncompressed size of an uploaded workbook / zip / project file |
| `ROI_MAX_ROWS_PER_TABLE` | `100000` | Maximum rows per template on import |
| `ROI_MAX_STORE_ROWS` | `500000` | Rows the workbench keeps in memory across all workspaces (≈ 2 KB per row); least recently used workspaces are evicted first |
| `ROI_MAX_PDF_JOBS` | `2` | PDF reports rendered at the same time; further requests wait up to 60 s, then get 503 |

Uploads are limited to 25 MB. A register with 10 000 contracts imports in about 3 seconds
([`docs/PERFORMANCE.md`](docs/PERFORMANCE.md)).

## Documentation

| Document | Content |
|---|---|
| [`docs/REGULATORY_MAPPING.md`](docs/REGULATORY_MAPPING.md) | Each check → DORA article / ITS provision (generated) |
| [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) | Templates, columns, requirement levels, code lists (generated) |
| [`docs/SAMPLE_DATA.md`](docs/SAMPLE_DATA.md) | The fictional Alpenrand group and the 25 injected errors (generated) |
| [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) | Regulatory details that must be verified |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Engineering decisions and their rationale |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Modules, data flow, report schema, extension guide |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Threat model (STRIDE), security controls and residual risks; disclosure policy in [`SECURITY.md`](SECURITY.md) |
| [`docs/UX.md`](docs/UX.md) | Personas, jobs to be done, screen flow, accessibility principles |
| [`docs/DEMO.md`](docs/DEMO.md) | 5-minute client demo with the Alpenrand sample |
| [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) | Timings for a 10 000-contract register, what was optimised, memory |
| [`CHANGELOG.md`](CHANGELOG.md) · [`docs/RELEASING.md`](docs/RELEASING.md) | Release history; how a version is tagged, built and published |

## Known limitations

- Not the official EBA validation rules or DPM; run your authority's validation before filing.
- The xBRL-CSV export is **best effort**: enumerations other than countries and currencies are
  exported with toolkit codes unless you provide a taxonomy code map
  (`--code-map`, see [`examples/code-map.example.json`](examples/code-map.example.json)).
- No GLEIF look-up (LEIs are checked for syntax and checksum only), no FX conversion.
- Licensed activities (B_06.01 c0020) are free text.
- The workbench keeps data in memory and has no authentication – run it locally or behind SSO.
- Per-finding validator messages are English; the interface, rule titles and explanations are
  English and German.

## Development

```bash
pip install -e ".[dev]"
```

```bash
make check        # ruff + mypy --strict + pytest with coverage (≥ 85 % enforced; currently ~98 %)
```

```bash
make docs         # regenerate the generated docs (a test fails if they are stale)
```

```bash
make examples     # regenerate examples/
```

```bash
npm install --no-save axe-core@4.10.3 && python -m pytest tests/e2e   # browser + WCAG tests
```

CI runs lint, strict type checking, tests on Python 3.11–3.13, a CLI smoke test and the
Playwright/axe-core end-to-end suite (which also regenerates the screenshots).

## License

[MIT](LICENSE)
