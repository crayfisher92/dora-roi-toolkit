# Regulatory assumptions

> **Read this before relying on the toolkit.** The toolkit was written from the structure
> of Regulation (EU) 2022/2554 (DORA) and the ESAs' Implementing Technical Standards on the
> register of information templates (adopted as Commission Implementing Regulation (EU)
> 2024/2956), *without* offline access to the authoritative texts, the EBA DPM/taxonomy or
> the EBA validation rules. Everything below is the authors' best understanding and **must
> be verified** against the versions in force and against your competent authority's
> reporting instructions before any supervisory use.

Each assumption has an ID so that code comments, tests and the regulatory mapping can refer
to it.

## Reconciliation status

| Status | Count | Meaning |
|---|---:|---|
| ✅ Confirmed | 0 | Verified against an official EBA/ESA source in `reference/eba/` |
| ✏️ Corrected | 0 | Changed in the code after comparison with an official source |
| ⏳ Open | all | Not yet verified |

**All assumptions below are still open.** The reconciliation against the official EBA
material (data model, list of possible values, validation/business checks, xBRL-CSV sample
package) has not been carried out yet: the folder `reference/eba/` it relies on is not in
the repository, and the EBA and EUR-Lex websites could not be reached from the build
environment. Nothing in this document should be read as confirmed.

Once the material is available the reconciliation proceeds as follows:

1. **Templates, columns, labels, M/C/O levels** (A-TPL-*) – compare the data model against
   `dora_roi.model.templates` (also printed in `docs/DATA_DICTIONARY.md`); correct codes,
   labels and requirement levels.
2. **Code lists** (A-CL-*, A-XBRL-05) – take the taxonomy member for every value from the list
   of possible values and ship it as the exporter's default code map, so that the xBRL-CSV
   export no longer needs `--code-map` for standard values.
3. **Validation rules** (A-VAL-*) – map every toolkit rule to the official check ID where
   one exists (new `official_ids` field on `Rule`, shown in `docs/REGULATORY_MAPPING.md`) and
   implement any official checks we are missing.
4. **xBRL-CSV structure** (A-XBRL-*) – run `roi check-package reference/eba/<sample>.zip`,
   which compares layout, `report.json`, parameters, filing indicators, table headers and
   per-column value styles (e.g. `eba_GA:*`) with our export, then fix every ❌.
5. Mark each assumption below as ✅ confirmed, ✏️ corrected (with the change) or ⏳ still
   open, and update the counts above.

## Templates and columns

| ID | Assumption |
|----|------------|
| A-TPL-01 | The register consists of 14 templates: B_01.01, B_01.02, B_01.03, B_02.01, B_02.02, B_02.03, B_03.01, B_03.02, B_03.03, B_04.01, B_05.01, B_05.02, B_06.01, B_07.01. |
| A-TPL-02 | Column codes follow the pattern `c0010`, `c0020`, … in the order listed in the ITS annex. The column *labels* used here paraphrase the ITS wording and may differ slightly from the published text. Where the published ITS uses a non-sequential code (e.g. `c0031`) the toolkit uses the next sequential code; check `docs/REGULATORY_MAPPING.md`. |
| A-TPL-03 | "Link" columns in B_02.03, B_03.01, B_03.02 and B_03.03 are technical boolean columns that are always `true`. |
| A-TPL-04 | B_02.02 has one row per combination of contractual arrangement, entity making use of the service, provider, function and ICT service type (its key). |
| A-TPL-05 | Arrangements without an end date are reported with end date `9999-12-31`. |
| A-TPL-06 | Notice periods (B_02.02 c0100/c0110) are expressed in calendar days; RTO/RPO (B_06.01 c0080/c0090) in hours. |
| A-TPL-07 | B_05.02 (supply chain): the direct ICT third-party provider of the arrangement is reported at **rank 1** with no recipient; a subcontractor of a rank *n* provider is reported at rank *n + 1* with the rank *n* provider as "recipient of sub-contracted ICT services". |
| A-TPL-08 | B_05.01 c0110/c0120 (ultimate parent) are mandatory; a provider that is its own ultimate parent reports its own code. |
| A-TPL-09 | B_06.01 c0020 "licensed activity" is accepted as free text. The ITS defines a closed list of licensed activities derived from sectoral legislation which is not reproduced here. |
| A-TPL-10 | Requirement levels (M / C / O) per column are the authors' reading of the ITS instructions and are encoded in `src/dora_roi/model/templates.py`. Several columns that the ITS describes as "mandatory if …" are modelled as *conditional* with a machine-checked condition. |

## Code lists

| ID | Assumption |
|----|------------|
| A-CL-01 | ICT service types follow a 19-value taxonomy S01–S19 (ICT project management … Cloud services: SaaS). |
| A-CL-02 | Entity types follow DORA Art. 2(1) plus a residual "other" value for non-financial group entities. |
| A-CL-03 | Values for contract type, hierarchy in group, termination reason, data sensitivity, reliance level, criticality, impact, substitutability, reason for non-substitutability and reintegration paraphrase the ITS options. Internal codes are toolkit-specific; the exporter's mapping to EBA taxonomy members (`eba_XX:xNN`) is a **placeholder** that must be completed from the taxonomy release. |
| A-CL-04 | Provider identification codes are of type LEI or EUID; additional codes may be CRN, VAT, passport number, national identity number, BIC or other. |

## Reference data

| ID | Assumption |
|----|------------|
| A-REF-01 | Countries are ISO 3166-1 alpha-2 (249 officially assigned codes; `XK` and EU-specific `EL`/`UK` are rejected with a hint). |
| A-REF-02 | Currencies are active ISO 4217 codes excluding funds, precious metals and testing codes. `HRK` (replaced by EUR in 2023) is rejected; `BGN` is still accepted although Bulgaria adopted the euro on 1 January 2026 — a warning-level check may be added. |
| A-REF-03 | LEI validation implements ISO 17442 syntax and the ISO 7064 MOD 97-10 checksum. It does **not** check that the LEI is registered/active in GLEIF. |

## Validation rules

| ID | Assumption |
|----|------------|
| A-VAL-01 | The toolkit's rules are **not** the EBA validation rules (the published `v****_m` DPM checks). They are an independent set derived from the ITS structure and DORA obligations and overlap substantially with, but do not replicate, the official checks. Run the official validation (e.g. your authority's portal or an EBA-taxonomy-aware XBRL processor) before submission. |
| A-VAL-02 | Severities are the authors' judgement: *error* = would make the register incomplete or inconsistent; *warning* = likely data-quality or supervisory-expectation issue; *info* = for awareness. They can be overridden per rule (`ValidationConfig.severity_overrides`). |
| A-VAL-03 | "Critical function has an exit plan" (BUS-019) is checked per ICT service supporting a critical or important function, using B_07.01 c0080 (DORA Art. 28(8)). |
| A-VAL-04 | The 12-month criticality reassessment (BUS-017) and 3-year audit (BUS-022) thresholds are configurable heuristics, not regulatory limits. DORA requires risk-based frequencies. |
| A-VAL-05 | Amounts are expected in the reporting currency of the entity maintaining the register (BUS-008, warning). |
| A-REG-01 | DORA references are to articles of Regulation (EU) 2022/2554. ITS references are given at annex/template level; article numbers of the ITS were deliberately not cited because they could not be verified. |

## xBRL-CSV export

| ID | Assumption |
|----|------------|
| A-XBRL-01 | The report package is a zip whose single top-level folder contains `META-INF/reportPackage.json` and `reports/` with `report.json`, `parameters.csv`, `FilingIndicators.csv` and one `b_XX.YY.csv` file per reported template whose header row is the column codes. |
| A-XBRL-02 | `report.json` extends the entry point `http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/dora/4.0/mod/dora.json` (configurable: `XbrlCsvOptions.entry_point`). The framework/taxonomy version in force must be checked. |
| A-XBRL-03 | `parameters.csv` contains `entityID` (`rs:<LEI>.<CON|IND>`), `refPeriod`, `baseCurrency` (`iso4217:XXX`), `decimalsInteger` and `decimalsMonetary`; the scheme prefix, level suffix and decimals are configurable. |
| A-XBRL-04 | Package name follows `<LEI>.<level>_<country>_<module code>_<module>_<reference date>_<timestamp>` (configurable / overridable). |
| A-XBRL-05 | Countries are exported as `eba_GA:<ISO code>` and currencies as `eba_CU:<ISO code>`. Other enumerations are exported with **toolkit-internal codes** unless a code map (`--code-map map.json`) supplies the taxonomy member for each value; the exporter warns when this happens. |
| A-XBRL-06 | Templates without rows are not written and have filing indicator `false`. |

## Analytics

| ID | Assumption |
|----|------------|
| A-AN-01 | Spend is taken from B_02.01 c0050 (annual cost of the arrangement) in the reporting currency; arrangements with several direct providers are split equally; other currencies are excluded, not converted. |
| A-AN-02 | Concentration is measured on the **ultimate parent** of each provider (B_05.01 c0110), so that subsidiaries of the same hyperscaler are aggregated. |
| A-AN-03 | HHI bands (1 500 / 2 500) are borrowed from competition analysis and used as a communication heuristic; DORA sets no numeric concentration threshold. |
| A-AN-04 | The "hidden concentration" metric counts the arrangements in whose B_05.02 chain a provider appears at rank ≥ 2. |
| A-AN-05 | Thresholds for key messages (single group ≥ 25 % of spend, ≥ 5 critical functions per group, ≥ 20 % spend with third-country groups, chain rank ≥ 3, expiry within 365 days) are configurable defaults (`AnalyticsConfig`). |

## DORA Art. 30 contract checklist

`reference/eu/` (official texts) is not in the repository, so the checklist was written from
the authors' knowledge of Regulation (EU) 2022/2554 and **all items below are open**.

| ID | Assumption |
|----|------------|
| A-A30-01 | The checklist covers Art. 30(1), the nine points (a)–(i) of Art. 30(2) and the six points (a)–(f) of Art. 30(3), with (2)(a), (2)(b), (3)(e) and (3)(f) split into their elements – 22 items in total (`docs/ART30_CHECKLIST.md`). Titles, requirement texts and remediation advice **paraphrase** the regulation in English and German; they are not quotations of the official language versions. |
| A-A30-02 | Art. 30(3) applies when at least one B_02.02 row of the arrangement links it to a function assessed as critical or important in B_06.01 (c0050). An arrangement whose function is not (yet) assessed is treated as not critical. |
| A-A30-03 | Art. 28(7) termination circumstances are checked as part of Art. 30(2)(h) (termination rights), not as a separate item. The RTS specifying the elements of Art. 30(2)(a) for subcontracting of ICT services supporting critical or important functions (mandate in Art. 30(5); believed to be Commission Delegated Regulation (EU) 2025/532 – **number to be verified**) is referenced but not broken down into items. |
| A-A30-04 | Inheritance of an overarching arrangement's assessment by its subsequent arrangements (D-049) is a practical convention, not a regulatory rule; competent authorities may expect each arrangement to be documented. |
| A-A30-05 | Priorities and target dates (D-050) are a methodology choice; DORA sets no remediation deadlines for contracts that pre-date its application. |
| A-A30-06 | Standard contractual clauses under Art. 30(4) are not assessed. |

## Major ICT-related incident classification

Written without access to the official texts (`reference/eu/` absent). **All open.**

| ID | Assumption |
|----|------------|
| A-INC-01 | The classification RTS is Commission Delegated Regulation (EU) 2024/1772; criteria are in its Art. 1–7 and the materiality thresholds in Art. 9 (cited as "RTS Art. 9(1)…(6)"). The reporting RTS with time limits is Commission Delegated Regulation (EU) 2025/301. Article numbers are cited for orientation and must be verified. |
| A-INC-02 | An incident is major if it affects *critical services* and either (a) involves a successful, malicious, unauthorised access to network and information systems that may result in data losses, or (b) meets the thresholds of two or more of the other six criteria. |
| A-INC-03 | Thresholds: clients > 10 % of the service's clients or > 100 000 clients; financial counterparts > 30 %; transactions > 10 % of the daily average number or value; any relevant client/counterpart affected; reputational impact if any of media coverage, repeated complaints, regulatory requirements not met, likely client loss; duration > 24 h or downtime of services supporting critical or important functions > 2 h; impact in ≥ 2 Member States; any adverse impact on availability, authenticity, integrity or confidentiality of data; costs and losses > EUR 100 000. Comparisons are "higher than". No absolute transaction-amount threshold is applied. |
| A-INC-04 | Reporting: initial notification within 4 h of classification and at the latest 24 h after awareness; intermediate report within 72 h of the initial notification; final report within one month of the latest intermediate report. Any relief for weekends/bank holidays, and entity-type exemptions from it, are **not** modelled (deadlines are conservative). Reporting templates and their content are out of scope. |
| A-INC-05 | Recurring incidents: individually non-major incidents with the same apparent root cause occurring at least twice within 6 months are assessed together; the toolkit aggregates them by adding counts, durations, downtime and costs, taking the largest denominator, OR-ing yes/no answers and uniting Member States. The RTS may prescribe a different aggregation; the monthly assessment cycle is not enforced. |
| A-INC-06 | "Critical services affected" is answered by the user; the register only provides a hint (linked arrangements supporting critical or important functions). Financial services requiring authorisation are not derived from the register. |
| A-INC-07 | Root-cause categories paraphrase those of the reporting templates and are used for information only. Significant cyber threats (voluntary notification) are out of scope. |

## Swiss angle (FINMA)

The circulars were not available offline. **All open.**

| ID | Assumption |
|----|------------|
| A-FINMA-01 | FINMA Circular 2018/3 "Outsourcing – banks and insurers" requires an up-to-date inventory of outsourced functions (description of the function, provider and sub-providers, service recipient, responsible unit, significance), careful selection, instruction and monitoring of the provider, security and continuity, audit and information rights for the company, its audit firm and FINMA, specific safeguards for outsourcing abroad (enforceable audit rights, restructuring/resolution, access to information from Switzerland) and a written contract. Topics are paraphrased; margin numbers are deliberately not cited. Whether a revision of the circular is in force must be checked. |
| A-FINMA-02 | FINMA Circular 2023/1 "Operational risks and resilience – banks" requires, among others, ICT and cyber risk management (incl. an ICT inventory and third-party dependencies), management of critical data, business continuity management (BIA, recovery objectives, tested plans) and operational resilience (identification of critical functions, tolerances for disruption, mapping to resources incl. third parties, scenario testing). |
| A-FINMA-03 | DORA "critical or important functions" and FINMA "significant functions" / "critical functions" overlap but are not identical; RTO (B_06.01 c0080) approximates but is not a tolerance for disruption. The mapping marks these as *partly covered*. |
| A-FINMA-04 | FINMA expects the reporting of cyber attacks under its own guidance (believed to be FINMA Guidance 05/2020, with different time limits from DORA); the toolkit does not compute FINMA deadlines. |
| A-FINMA-05 | FINMA Circ. 2018/3 is assumed to apply at group level through consolidated supervision for a Swiss group with EU subsidiaries; the toolkit's group view rests on this assumption. |
