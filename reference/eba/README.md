# Official EBA reference material for DORA RoI reconciliation

Unmodified copies of the material the European Banking Authority publishes on its page
[Preparations for reporting of DORA registers of information](https://eba.europa.eu/activities/direct-supervision-and-oversight/digital-operational-resilience-act/preparation-dora-application),
downloaded on 2026-11-14. They are © European Banking Authority and are reproduced here with
acknowledgement of the source, only so that the reconciliation in
[`docs/ASSUMPTIONS.md`](../../docs/ASSUMPTIONS.md) can be repeated and tested.

All of it refers to **EBA reporting framework 4.0** (DPM 4.0, taxonomy package 4.0 errata 5),
as used for the registers reported in 2025. Check the
[EBA reporting frameworks](https://www.eba.europa.eu/risk-and-data-analysis/reporting-frameworks)
for the version in force for a later reference date and refresh these files when it changes.

| File | What it is | Used for | SHA-256 of the downloaded file |
|---|---|---|---|
| `list-of-possible-values-2025-03-03.xlsx` | *List of possible values for all data fields with drop downs* (updated 3 March 2025) | Taxonomy members of every closed list → `dora_roi.model.eba_codes` (default xBRL-CSV code map), EBA country/currency lists | `a0fed557cc6837f909227088338408581cd413cce046566dcc7b4253ba009c9f` |
| `annotated-table-layout-dora-4.0-2024-12-17.xlsx` | *Annotated Table Layout DORA 4.0* (from `annotated_templates.zip`, 17 Dec 2024) | Column codes, primary keys, data types and hierarchies per template, B_99.01 | `b3063b698bb586bc3306ca106279c4e9db806e91f1d4f9fda33ba9d620a6a449` |
| `technical-checks-and-validation-rules-2025-04-28.xlsx` | *Overview of the RoI reporting technical checks and validation rules* (updated 28 April 2025) | Technical checks (1xx/7xx/8xx), DPM validation rules (v88xx/e23xxx, active/inactive), GLEIF/BRIS checks | `7e08314f17eca27a18c94b09a24f667c2046f09d57e7f1d4d20b5393ac43bd4e` |
| `licensed-activities-dpm-4.0.xlsx` | *ITS on RoI – Annex 2 list of licensed activities* (updated to DPM 4.0) | B_06.01 c0020 codes | `1f54e1002171852e79d3b7cd79496880d1926b15655f3513a977b867928874af` |
| `DUMMYLEI123456789012.CON_FR_DORA010100_DORA_2024-12-31_20241213174803429.zip` | Official DORA xBRL-CSV sample instance (from `sample_documents.zip` → `instances xBRL-CSV.zip`) | `roi check-package`, header/layout tests | `646ff6581cf63cf5de9578f2fddd0677ac22ea9e6280e85e55561f9f51431438` (inner zip) |
| `dora-roi-reporting-faq-2025-03-28.pdf` | *DORA RoI reporting FAQ* (updated 28 March 2025) | "Not Applicable" in key fields (Q26, Q59–Q64, Q124), own LEI as parent (Q58), rank-1 recipient (Q65), no termination reason for reported contracts (Q52) | `209cd01cbc7c55a34edc345df5913f7568be719fe00cd3472a6fb57751db58fc` |
| `data-model-for-dora-roi-2025-04.pdf` | *Data Model for DORA RoI* (April 2025) | Primary and foreign keys | `6ce5b150bd746b638b116341baac421310154f5c8b4e7180b06e6e2ddc94741a` |

Not copied (large or not DORA-specific), consulted from the same page:
[EBA Filing Rules v5.5](https://www.eba.europa.eu/sites/default/files/2025-01/1f92a6e9-9e5a-41e8-bd44-0dc757f754c2/EBA%20Filing%20Rules%20v5.5_2025_01_14%20%281%29.pdf)
(SHA-256 `f250b79733c2b2191dfebd3ad5393adcd2c351354a0c244848126ea24ec4d361`), the full
`annotated_templates.zip` (`3b973e7e…a57d`) and `sample_documents.zip` (`2183cdd2…ecac`).
