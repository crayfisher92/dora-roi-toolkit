# Regulatory assumptions

> **Read this before relying on the toolkit.** The toolkit was first written from the
> structure of Regulation (EU) 2022/2554 (DORA) and the ESAs' Implementing Technical Standards
> on the register of information templates (Commission Implementing Regulation (EU)
> 2024/2956) without access to the EBA material. The register data model, code lists and
> xBRL-CSV export have since been **reconciled against the official EBA files** for reporting
> framework 4.0 (see [`reference/eba/`](../reference/eba/README.md)); the validation rules
> and the DORA programme modules (Art. 30, incidents, FINMA) have not. It remains an
> unofficial tool: verify against the versions in force and your competent authority's
> reporting instructions before any supervisory use.

Each assumption has an ID so that code comments, tests and the regulatory mapping can refer
to it. Status: ✅ confirmed against an official source · ✏️ corrected after comparison ·
⏳ open (not verified).

## Reconciliation status

Reconciled on 2026-11-14 against the EBA files in `reference/eba/` (reporting framework 4.0):
annotated table layout DORA 4.0, list of possible values (3 March 2025), overview of technical
checks and validation rules (28 April 2025), list of licensed activities, the official DORA
xBRL-CSV sample instance, the DORA RoI reporting FAQ (28 March 2025) and the data model.
`tests/test_eba_reference.py` and `tests/test_package_check.py` re-check the column codes,
primary keys, generated code tables and the package layout against these files.

| Area | ✅ | ✏️ | ⏳ |
|---|---:|---:|---:|
| Templates and columns (A-TPL) | 4 | 5 | 2 |
| Code lists (A-CL) | 1 | 3 | 0 |
| Reference data (A-REF) | 1 | 2 | 0 |
| Validation rules (A-VAL, A-REG) | 0 | 1 | 6 |
| xBRL-CSV export (A-XBRL) | 4 | 3 | 0 |
| Analytics, Art. 30, incidents, FINMA | 0 | 0 | all |

Still to do, in this order:

1. **Validation rules** (A-VAL-01, A-VAL-06) – map every toolkit rule to the official check
   ID where one exists (DPM rules `v88xx_m` / `e236xx_e`, technical checks 7xx/8xx, GLEIF/BRIS
   checks `VR_*`), implement the missing ones and align severities; resolve BUS-002 (A-VAL-06).
2. **Requirement levels** (A-TPL-10) – re-baseline M/C/O per column against the ITS
   instructions, the FAQ and the DPM existence/completeness rules (e.g. v8881/v8882 RTO/RPO,
   v8885 audit date, v8865 deletion date), updating the sample generator accordingly.
3. **B_99.01** (A-TPL-11) – model the definitions template instead of reporting it empty.
4. **Framework version** (A-XBRL-02) – confirm the framework, entry point and filing rules
   valid for each reference date; refresh `reference/eba/` and run
   `python scripts/gen_eba_codes.py` when the EBA publishes a new version.

## Templates and columns

| ID | Status | Assumption |
|----|:---:|------------|
| A-TPL-01 | ✏️ | The register consists of the 14 templates B_01.01 … B_07.01 modelled by the toolkit **plus B_99.01** (definitions from entities making use of the ICT services), which the DPM 4.0 defines and the official sample reports. See A-TPL-11. |
| A-TPL-02 | ✏️ | Column codes follow the annotated table layout DORA 4.0 exactly. B_03.03 "Link" is **c0031** (was c0030); B_03.02 has **no** "Link" column (the toolkit had c0040). The importer still reads workbooks with the old codes. Labels paraphrase the ITS. |
| A-TPL-03 | ✏️ | The technical "Link" columns are B_02.03 c0030, B_03.01 c0030 and B_03.03 c0031, reported as `true` (DPM `trueItemType`). |
| A-TPL-04 | ✏️ | B_02.02 primary key per the data model / annotated layout: c0010, c0020, c0030, c0050, c0060, **c0130, c0150, c0160** – one row per country of provision, storage and processing (FAQ Q37, Q117). The toolkit's key previously omitted the three countries. |
| A-TPL-05 | ✅ | Arrangements without an end date are reported with end date `9999-12-31`. |
| A-TPL-06 | ⏳ | Notice periods (B_02.02 c0100/c0110) are expressed in calendar days; RTO/RPO (B_06.01 c0080/c0090) in hours. |
| A-TPL-07 | ✏️ | B_05.02: the direct ICT third-party service provider is at **rank 1** and is **its own recipient** – c0060 repeats c0030 (FAQ Q65); a subcontractor of a rank *n* provider is at rank *n + 1* with the rank *n* provider as recipient (FAQ Q81). Inside the toolkit the rank-1 recipient is held empty; the exporter writes the provider's own code. |
| A-TPL-08 | ✅ | B_05.01 c0110/c0120 (ultimate parent) are mandatory; a provider that is its own ultimate parent reports its own code (FAQ Q99). |
| A-TPL-09 | ✅ | B_06.01 c0020 "licensed activity" is a closed list (DPM hierarchy TA5, ITS Annex IV; 131 members in `reference/eba/licensed-activities-dpm-4.0.xlsx`). The toolkit accepts the member or its label and exports the member; values outside the list are exported as given with a warning. A validation rule for the list is still to be added. |
| A-TPL-10 | ⏳ | Requirement levels (M / C / O) per column are the authors' reading of the ITS instructions (`src/dora_roi/model/templates.py`). B_02.02 c0130 was changed from M to C (FAQ Q59). Known differences still to resolve: DPM rules v8881/v8882 expect RTO/RPO for every function, v8885 the audit date (9999-12-31 if none), v8865 the deletion date. |
| A-TPL-11 | ✅ | Empty key / foreign-key fields are reported as "Not Applicable" (text) or `eba_GA:qx2007` (countries) – B_02.01 c0030, B_02.02 c0130/c0150/c0160, B_04.01 c0040 (FAQ Q26, Q59–Q64, Q124) – and an entity without a direct parent repeats its own LEI in B_01.02 c0060 (FAQ Q58). The toolkit holds these as empty values and applies the conventions on export; the importer reads them back as empty. B_99.01 is reported empty for now. |

## Code lists

| ID | Status | Assumption |
|----|:---:|------------|
| A-CL-01 | ✅ | ICT service types S01–S19 match the EBA list (hierarchy TA4, members `eba_TA:S01` … `eba_TA:S19`). |
| A-CL-02 | ✏️ | Entity types follow the EBA hierarchies CT6 (22 financial-entity types; B_01.01) and CT61 (+ two non-financial values; B_01.02). Insurance and reinsurance undertakings are **one** value; "other financial entity" and "non-financial entity: ICT intra-group service provider" were added; `OTHER` now means "non-financial entity: other than ICT intra-group service provider". |
| A-CL-03 | ✏️ | Every code list has its taxonomy member in `dora_roi.model.eba_codes.CODE_MAP`, taken from the EBA list of possible values; this is the exporter's default code map. Corrections: hierarchy in group `OTHER` → `OUTSOURCING` ("service provider to which the financial entity outsources all its operational activities"); impact of discontinuing gained "assessment not performed"; reason for non-substitutability gained "not applicable"; B_07.01 c0110 is a three-value list (yes / no / assessment not performed), not a boolean; B_02.02 c0140, B_04.01 c0030 and B_07.01 c0080 are enumerations (`eba_BT:x28/x29`, `eba_ZZ:x838/x839`). |
| A-CL-04 | ✏️ | Provider identification codes may be LEI, EUID, CRN, VAT, passport number or national code (hierarchy qCO:new_CO2) for both the main and the additional code; BIC and "other" are not in the list and were removed. |

## Reference data

| ID | Status | Assumption |
|----|:---:|------------|
| A-REF-01 | ✏️ | Countries are the 250 members of the DPM country hierarchy: the 249 ISO 3166-1 alpha-2 codes **plus `XK`** (Kosovo), which the EBA list includes. `EL`/`UK` are rejected with a hint. |
| A-REF-02 | ✏️ | Currencies are active ISO 4217 codes excluding funds, precious metals and testing codes. The DPM 4.0 currency hierarchy lags ISO 4217 (it lacks e.g. MRU, SLE, STN, VES, VED, ZWG, XCG, XAF, XOF and still has HRK); the exporter warns when a value is not in the DPM list. `BGN` is still accepted although Bulgaria adopted the euro on 1 January 2026. |
| A-REF-03 | ✅ | LEI validation implements ISO 17442 syntax and the ISO 7064 MOD 97-10 checksum. It does **not** check that the LEI is registered/active in GLEIF (the ESAs do: checks VR_2, VR_12, VR_23, VR_71, VR_77; EUIDs against BRIS: VR_72, VR_78). |

## Validation rules

| ID | Status | Assumption |
|----|:---:|------------|
| A-VAL-01 | ⏳ | The toolkit's rules are **not** the EBA validation rules. The official set (technical checks 1xx/7xx/8xx, DPM rules `v88xx_m`/`e236xx_e` with their active/inactive status, GLEIF/BRIS checks) is now in `reference/eba/technical-checks-and-validation-rules-2025-04-28.xlsx`; mapping each toolkit rule to it is still to do. Run the official validation before submission. |
| A-VAL-02 | ⏳ | Severities are the authors' judgement: *error* = would make the register incomplete or inconsistent; *warning* = likely data-quality or supervisory-expectation issue; *info* = for awareness. They can be overridden per rule (`ValidationConfig.severity_overrides`). The ESAs report almost all DPM rules as warnings. |
| A-VAL-03 | ⏳ | "Critical function has an exit plan" (BUS-019) is checked per ICT service supporting a critical or important function, using B_07.01 c0080 (DORA Art. 28(8)). A missing exit plan is a compliance finding, not a reporting error. |
| A-VAL-04 | ⏳ | The 12-month criticality reassessment (BUS-017) and 3-year audit (BUS-022) thresholds are configurable heuristics, not regulatory limits. DORA requires risk-based frequencies. |
| A-VAL-05 | ⏳ | Amounts are expected in the reporting currency of the entity maintaining the register (BUS-008, warning). |
| A-VAL-06 | ✏️ | Corrected after the FAQ: BUS-010 accepts an entity's own LEI as parent when it has no direct parent (Q58) and flags another LEI; SC-004 accepts the provider itself as rank-1 recipient (Q65) and flags another code; FLD-013 applies the EUID format only to EUIDs. **Open:** BUS-002 still requires a termination reason for arrangements that ended on or before the reference date, whereas FAQ Q52 says the register contains only arrangements in force and c0090 stays empty; changing it needs the sample data and its expectations to change too. |
| A-REG-01 | ⏳ | DORA references are to articles of Regulation (EU) 2022/2554. ITS references are given at annex/template level; article numbers of the ITS were deliberately not cited because they could not be verified. FAQ references are to the EBA DORA RoI reporting FAQ of 28 March 2025. |

## xBRL-CSV export

| ID | Status | Assumption |
|----|:---:|------------|
| A-XBRL-01 | ✅ | The report package is a zip whose single top-level folder contains `META-INF/reportPackage.json` and `reports/` with `report.json`, `parameters.csv`, `FilingIndicators.csv` and one `b_XX.YY.csv` file per template whose header row is the column codes (official sample; technical check 701). Column order is not significant. |
| A-XBRL-02 | ✅ | `report.json` extends `http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/dora/4.0/mod/dora.json` (official sample, framework 4.0; configurable). Whether a later framework applies to a given reference date must still be checked. |
| A-XBRL-03 | ✅ | `parameters.csv` contains `entityID` (`rs:<LEI>.CON` or `.IND`), `refPeriod`, `baseCurrency` (`iso4217:XXX`), `decimalsInteger` and `decimalsMonetary` (official sample; checks 714, 723). The level is restricted to CON/IND (the toolkit previously also offered `SUB`). |
| A-XBRL-04 | ✅ | Package name follows `<LEI>.<level>_<country>_<module code>_<module>_<reference date>_<timestamp>` with module code `DORA010100` (official sample; check 105). |
| A-XBRL-05 | ✏️ | Countries are exported as `eba_GA:<ISO code>`, currencies as `eba_CU:<ISO code>` and **all other enumerations as their taxonomy members** from the official code map (`--code-map` only overrides single values). |
| A-XBRL-06 | ✏️ | **Every** template is reported – empty ones as a header-only file – and every filing indicator is `true` (technical check 808), including B_99.01. The toolkit previously omitted empty templates with indicator `false`, which the ESAs reject. |
| A-XBRL-07 | ✏️ | The non-standard `x-dora-roi-toolkit` member was removed from `report.json`. |

## Analytics

| ID | Assumption |
|----|------------|
| A-AN-01 | Spend is taken from B_02.01 c0050 (annual cost of the arrangement) in the reporting currency; arrangements with several direct providers are split equally; other currencies are excluded, not converted. |
| A-AN-02 | Concentration is measured on the **ultimate parent** of each provider (B_05.01 c0110), so that subsidiaries of the same hyperscaler are aggregated. |
| A-AN-03 | HHI bands (1 500 / 2 500) are borrowed from competition analysis and used as a communication heuristic; DORA sets no numeric concentration threshold. |
| A-AN-04 | The "hidden concentration" metric counts the arrangements in whose B_05.02 chain a provider appears at rank ≥ 2. |
| A-AN-05 | Thresholds for key messages (single group ≥ 25 % of spend, ≥ 5 critical functions per group, ≥ 20 % spend with third-country groups, chain rank ≥ 3, expiry within 365 days) are configurable defaults (`AnalyticsConfig`). |
