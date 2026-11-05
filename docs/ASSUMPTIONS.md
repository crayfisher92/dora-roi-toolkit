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
