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
primary keys, generated code tables and the package layout against these files. The
requirement level of every column was re-checked against the reporting instructions in the
Annex of the ITS as published in the Official Journal (Commission Implementing Regulation
(EU) 2024/2956, <https://eur-lex.europa.eu/eli/reg_impl/2024/2956/oj>), which FAQ Q33 names
as the source of the mandatory fields, and against the DPM existence rules.

| Area | ✅ | ✏️ | ⏳ |
|---|---:|---:|---:|
| Templates and columns (A-TPL) | 5 | 6 | 0 |
| Code lists (A-CL) | 1 | 3 | 0 |
| Reference data (A-REF) | 1 | 2 | 0 |
| Validation rules (A-VAL, A-REG) | 0 | 2 | 5 |
| xBRL-CSV export (A-XBRL) | 4 | 3 | 0 |
| Analytics, Art. 30, incidents, FINMA | 0 | 0 | all |

Still to do:

1. **DORA in framework 4.4 phase 2** (A-XBRL-02) – the EBA plans technical amendments to the DORA DPM and taxonomy from reference date 12/2027. When the package is published, add it to `reference/eba/`, run `python scripts/gen_eba_codes.py`, re-run the reference tests and add its entry point to `FRAMEWORK_VERSIONS` in `dora_roi.io.xbrl_csv`.

## Templates and columns

| ID | Status | Assumption |
|----|:---:|------------|
| A-TPL-01 | ✏️ | The register consists of the 14 ITS templates B_01.01 … B_07.01 **plus B_99.01** (definitions from entities making use of the ICT services), which the DPM 4.0 defines and the official sample reports. The toolkit models B_99.01 as a 15th template: one optional row of 19 free-text columns with the entity's internal definition of each option of six closed lists (contract type, data sensitivity, impact of discontinuing the function, substitutability, reintegration, impact of discontinuing the ICT services – e.g. how it assesses data sensitivity, FAQ Q67). It is a closed table without key columns; FLD-011 flags more than one row, an input without a B_99.01 sheet raises no IMP-002 warning, and an empty B_99.01 is exported header-only. |
| A-TPL-02 | ✏️ | Column codes follow the annotated table layout DORA 4.0 exactly. B_03.03 "Link" is **c0031** (was c0030); B_03.02 has **no** "Link" column (the toolkit had c0040). The importer still reads workbooks with the old codes. Labels paraphrase the ITS. |
| A-TPL-03 | ✏️ | The technical "Link" columns are B_02.03 c0030, B_03.01 c0030 and B_03.03 c0031, reported as `true` (DPM `trueItemType`). |
| A-TPL-04 | ✏️ | B_02.02 primary key per the data model / annotated layout: c0010, c0020, c0030, c0050, c0060, **c0130, c0150, c0160** – one row per country of provision, storage and processing (FAQ Q37, Q117). The toolkit's key previously omitted the three countries. |
| A-TPL-05 | ✅ | Arrangements without an end date are reported with end date `9999-12-31`. |
| A-TPL-06 | ✅ | Notice periods (B_02.02 c0100/c0110) are expressed in calendar days; RTO/RPO (B_06.01 c0080/c0090) in hours – less than one hour is reported as 1, an undefined objective as 0 (ITS Annex, B_06.01.0090/0100). |
| A-TPL-07 | ✏️ | B_05.02: the direct ICT third-party service provider is at **rank 1** and is **its own recipient** – c0060 repeats c0030 (FAQ Q65); a subcontractor of a rank *n* provider is at rank *n + 1* with the rank *n* provider as recipient (FAQ Q81). Inside the toolkit the rank-1 recipient is held empty; the exporter writes the provider's own code. |
| A-TPL-08 | ✅ | B_05.01 c0110/c0120 (ultimate parent) are mandatory; a provider that is its own ultimate parent reports its own code (FAQ Q99). |
| A-TPL-09 | ✅ | B_06.01 c0020 "licensed activity" is a closed list (DPM hierarchy TA5, ITS Annex IV; 131 members in `reference/eba/licensed-activities-dpm-4.0.xlsx`). The toolkit accepts the member or its label and exports the member; values outside the list are reported by FLD-015 and exported as given with a warning. |
| A-TPL-10 | ✏️ | Requirement levels (M / C / O) follow the ITS reporting instructions; conditional columns are checked by FLD-014 and the BUS rules. Corrected: B_02.02 c0100, c0110, c0120, c0140 and c0180 are mandatory only when the ICT service supports a critical or important function (were M), c0170 only when data is also stored (BUS-005); B_01.02 c0110 total assets only for financial entities and c0100 only with c0110 (were M); B_05.01 c0100 only for direct providers and c0090 only with c0100 (were M); B_01.02 c0090 deletion date (9999-12-31 while not deleted), B_05.01 c0060 name in Latin alphabet, B_06.01 c0080/c0090 RTO/RPO (0 = not defined) and B_07.01 c0070 audit date (9999-12-31 = no audit) are mandatory (were O or C, DPM rules v8865, e23674, v8881/v8882, v8885); B_06.01 c0060 reasons and B_07.01 c0120 alternatives are optional (were C), so BUS-015 and BUS-021 are warnings. Deliberate deviation: B_01.02 c0060 (parent LEI, M in the ITS) stays C because an empty value means 'no direct parent' and the export writes the entity's own LEI (FAQ Q58). |
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
| A-VAL-01 | ✏️ | The toolkit's rules are not the EBA validation rules, but they are now **mapped** to them: `dora_roi.validation.eba_mapping` lists for each rule the official checks it implements (technical checks, DPM rules `v88xx_m`/`e236xx_e`, GLEIF/BRIS checks `VR_*`, generated from `reference/eba/technical-checks-and-validation-rules-2025-04-28.xlsx`), and [REGULATORY_MAPPING.md](REGULATORY_MAPPING.md#coverage-of-the-official-eba-checks) shows every official check with the rules that implement it or how it is met otherwise (xBRL-CSV export, the authority's platform, online lookup). Tests fail if an active official check is neither implemented nor explained, or if a column required by a DPM existence or completeness rule is not mandatory. Not checkable offline: whether an LEI or EUID exists in GLEIF/BRIS (VR_2, VR_12, VR_23, VR_71, VR_72, VR_77, VR_78 – format and check digits are checked) and the GLEIF country (VR_16). New with the mapping: FLD-015 (licensed activity and currency outside the EBA lists, check 503) and FLD-013 for the additional provider code. Run the official validation before submission. |
| A-VAL-02 | ⏳ | Severities are the authors' judgement: *error* = would make the register incomplete or inconsistent; *warning* = likely data-quality or supervisory-expectation issue; *info* = for awareness. They can be overridden per rule (`ValidationConfig.severity_overrides`). The ESAs report almost all DPM rules as warnings. |
| A-VAL-03 | ⏳ | "Critical function has an exit plan" (BUS-019) is checked per ICT service supporting a critical or important function, using B_07.01 c0080 (DORA Art. 28(8)). A missing exit plan is a compliance finding, not a reporting error. |
| A-VAL-04 | ⏳ | The 12-month criticality reassessment (BUS-017) and 3-year audit (BUS-022) thresholds are configurable heuristics, not regulatory limits. DORA requires risk-based frequencies. |
| A-VAL-05 | ⏳ | Amounts are expected in the reporting currency of the entity maintaining the register (BUS-008, warning). |
| A-VAL-06 | ✏️ | Corrected after the FAQ: BUS-010 accepts an entity's own LEI as parent when it has no direct parent (Q58) and flags another LEI; SC-004 accepts the provider itself as rank-1 recipient (Q65) and flags another code; FLD-013 applies the EUID format only to EUIDs; BUS-002 warns about arrangements that ended before the reference date and BUS-003 about any termination reason, because only arrangements in force are reported and c0090 stays empty (Q52–53). No active EBA check compares the end date with the reference date (v8816_m, end after start, was deactivated in March 2025), so both are warnings. |
| A-REG-01 | ⏳ | DORA references are to articles of Regulation (EU) 2022/2554. ITS references are given at annex/template level; article numbers of the ITS were deliberately not cited because they could not be verified. FAQ references are to the EBA DORA RoI reporting FAQ of 28 March 2025. |

## xBRL-CSV export

| ID | Status | Assumption |
|----|:---:|------------|
| A-XBRL-01 | ✅ | The report package is a zip whose single top-level folder contains `META-INF/reportPackage.json` and `reports/` with `report.json`, `parameters.csv`, `FilingIndicators.csv` and one `b_XX.YY.csv` file per template whose header row is the column codes (official sample; technical check 701). Column order is not significant. |
| A-XBRL-02 | ✅ | `report.json` extends `http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/dora/4.0/mod/dora.json` (official sample, framework 4.0; configurable). Checked on 15 November 2026: the DORA module of framework 4.0 applies to the reference dates 31 March 2025 and 31 December 2025 (national authorities state the taxonomy for the 2026 submission is unchanged), and no DORA change is scheduled before 12/2027 – releases 4.1 to 4.3 and 4.4 phase 1 leave the DORA module untouched – so it also applies to 31 December 2026. The EBA's framework 4.4 page lists technical amendments to the DORA DPM and taxonomy in phase 2 with first reference date 12/2027; the export warns for reference dates from December 2027 (`FRAMEWORK_VERSIONS`). Sources in [reference/eba/README.md](../reference/eba/README.md#framework-version-by-reference-date). |
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
