# DORA Register of Information – validation report

- **Entity:** Alpenrand Bank (Europe) AG (`3912RO6DCAXX71K9W972`)
- **Reference date:** 2025-12-31
- **Source:** alpenrand-sample.xlsx
- **Generated:** 2026-11-05 04:55 UTC (dora-roi-toolkit 0.1.0, 62 rules)

**Result: ❌ FAILED** — 27 error(s), 5 warning(s), 1 info.

## Findings by rule

| Rule | Severity | Title | Count | Supports |
|---|---|---|---:|---|
| `BUS-002` | error | Termination reason missing for an ended arrangement | 2 | ITS Annex II; DORA Art. 28(7) |
| `BUS-019` | error | No exit plan for an ICT service supporting a critical function | 2 | DORA Art. 28(8); DORA Art. 30(3) |
| `SC-003` | error | Subcontracting chain does not resolve | 2 | DORA Art. 28(3); DORA Art. 29; DORA Art. 30(2); ITS Annex II |
| `XRF-003` | error | ICT third-party service provider not listed in B_05.01 | 2 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3); DORA Art. 28(3) |
| `XRF-013` | error | Assessment does not match any ICT service in B_02.02 | 2 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3) |
| `BUS-001` | error | End date before start date | 1 | ITS Annex II |
| `BUS-004` | error | Data storage location missing | 1 | ITS Annex II; DORA Art. 30(2) |
| `BUS-015` | error | Critical function lacks justification or recovery objectives | 1 | ITS Annex II; DORA Art. 3(22); DORA Art. 28(4) |
| `BUS-018` | error | ICT service supporting a critical function not assessed in B_07.01 | 1 | DORA Art. 28(3); DORA Art. 29; ITS Annex I |
| `BUS-020` | error | Reason for non-substitutability missing | 1 | ITS Annex II; DORA Art. 29 |
| `FLD-001` | error | Mandatory value missing | 1 | DORA Art. 28(3); ITS Annex I; ITS Annex II |
| `FLD-002` | error | Invalid LEI | 1 | ISO 17442; ITS Art. – identification |
| `FLD-003` | error | Invalid date | 1 | ISO 8601; ITS Annex II |
| `FLD-004` | error | Value not in code list | 1 | ITS Annex II; ITS Annex III |
| `FLD-005` | error | Invalid country code | 1 | ISO 3166-1; ITS Annex II; DORA Art. 30(2) |
| `FLD-006` | error | Invalid currency code | 1 | ISO 4217; ITS Annex II |
| `FLD-010` | error | Duplicate record key | 1 | ITS Annex II; ITS Art. – consistency |
| `FLD-013` | error | Provider code inconsistent with its code type | 1 | ISO 17442; ITS Art. – identification |
| `SC-001` | error | Rank 1 provider is not the direct provider of the arrangement | 1 | DORA Art. 28(3); DORA Art. 29; DORA Art. 30(2); ITS Annex II |
| `XRF-001` | error | Contractual arrangement not defined in B_02.01 | 1 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3) |
| `XRF-004` | error | Function not identified in B_06.01 | 1 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3); DORA Art. 28(3); DORA Art. 3(22) |
| `XRF-006` | error | Contractual arrangement without specific information | 1 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3) |
| `XRF-008` | warning | Provider in B_02.02 not reported as signatory in B_03.02 | 2 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3) |
| `BUS-008` | warning | Currency differs from the reporting currency | 1 | ITS Annex II |
| `BUS-016` | warning | Criticality assessment not performed | 1 | DORA Art. 28(4); DORA Art. 3(22) |
| `XRF-010` | warning | Provider not used by any arrangement | 1 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3) |
| `XRF-014` | info | Parent undertaking outside the register scope | 1 | ITS Art. – consistency; ITS Annex II; DORA Art. 28(3) |

## Findings by template

| Template | Records | Errors | Warnings | Info |
|---|---:|---:|---:|---:|
| B_01.01 | 1 | 0 | 0 | 0 |
| B_01.02 | 3 | 0 | 0 | 1 |
| B_01.03 | 2 | 0 | 0 | 0 |
| B_02.01 | 121 | 3 | 1 | 0 |
| B_02.02 | 151 | 13 | 2 | 0 |
| B_02.03 | 0 | 0 | 0 | 0 |
| B_03.01 | 120 | 1 | 0 | 0 |
| B_03.02 | 118 | 0 | 0 | 0 |
| B_03.03 | 0 | 0 | 0 | 0 |
| B_04.01 | 144 | 1 | 0 | 0 |
| B_05.01 | 46 | 0 | 1 | 0 |
| B_05.02 | 166 | 3 | 0 | 0 |
| B_06.01 | 31 | 1 | 1 | 0 |
| B_07.01 | 106 | 5 | 0 | 0 |

## Findings

| Severity | Rule | Location | Record | Message |
|---|---|---|---|---|
| error | `FLD-006` | B_02.01 / row 23 / c0040 | AR-LU-0020 | c0040 'Currency of the amount reported': 'EURO' is not an active ISO 4217 currency code |
| error | `FLD-010` | B_02.01 / row 123 | CO-AT-0006 | Duplicate key (contract_ref) = 'CO-AT-0006' already reported in row 9 |
| error | `XRF-006` | B_02.01 / row 124 / c0010 | AR-LU-9002 | Contractual arrangement 'AR-LU-9002' has no row in B_02.02 |
| error | `BUS-004` | B_02.02 / row 4 / c0150 | MSA-DE-0001 \| 3912RO6DCAXX71K9W972 \| 5299XGE5RGK9SNVGG353 \| F-DE-02 \| S17 | Data is stored but the location of data at rest is not reported |
| error | `XRF-004` | B_02.02 / row 7 / c0050 | CO-LU-0002 \| 6354ZX2X914MZGYMMB68 \| 5299XGE5RGK9SNVGG353 \| F-LU-1 \| S17 | Function 'F-LU-1' is not identified in B_06.01 |
| error | `BUS-018` | B_02.02 / row 18 / c0010 | MSA-DE-0007 \| 3912RO6DCAXX71K9W972 \| 2138C2U0YRY1CYEQVJ54 \| F-DE-06 \| S17 | 'MSA-DE-0007' supports critical function 'F-DE-06' but has no assessment in B_07.01 |
| error | `FLD-013` | B_02.02 / row 38 / c0030 | AR-DE-0019 \| 3912RO6DCAXX71K9W972 \| 21381VQL0Y482P2BV900 \| F-DE-14 \| S03 | '21381VQL0Y482P2BV900' is typed as LEI but LEI checksum (ISO 17442 / MOD 97-10) failed; expected check digits 56 |
| error | `XRF-003` | B_02.02 / row 38 / c0030 | AR-DE-0019 \| 3912RO6DCAXX71K9W972 \| 21381VQL0Y482P2BV900 \| F-DE-14 \| S03 | Provider '21381VQL0Y482P2BV900' is not listed in B_05.01 |
| error | `FLD-003` | B_02.02 / row 40 / c0080 | AR-AT-0021 \| 8156AYQ5YUFTZEC92R45 \| 21381VQL0Y482P2BV956 \| F-AT-07 \| S03 | c0080 'End date of the contractual arrangement': '31/12/2027' is not a valid ISO 8601 date (YYYY-MM-DD) |
| error | `FLD-005` | B_02.02 / row 54 / c0120 | AR-DE-0034 \| 3912RO6DCAXX71K9W972 \| 63540HLDS88ODR38X136 \| F-DE-05 \| S19 | c0120 'Country of the governing law of the contractual arrangement': 'UK' is not an ISO 3166-1 alpha-2 country code (did you mean 'GB'?) |
| error | `FLD-004` | B_02.02 / row 71 / c0060 | AR-LU-0050 \| 6354ZX2X914MZGYMMB68 \| 8945J54J0JEU0CJ1E554 \| F-LU-07 \|  | c0060 'Type of ICT services': 'S20' is not a valid IctServiceType code (allowed: S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19) |
| error | `FLD-001` | B_02.02 / row 77 / c0120 | AR-AT-0056 \| 8156AYQ5YUFTZEC92R45 \| 7245TLYA2OZHE7KGQP74 \| F-AT-05 \| S19 | Mandatory column c0120 'Country of the governing law of the contractual arrangement' is empty |
| error | `BUS-001` | B_02.02 / row 84 / c0080 | AR-LU-0062 \| 6354ZX2X914MZGYMMB68 \| 8156RHZ6DZDLTDXWN816 \| F-LU-08 \| S19 | End date 2023-04-30 is before start date 2024-05-01 |
| error | `BUS-002` | B_02.02 / row 84 / c0090 | AR-LU-0062 \| 6354ZX2X914MZGYMMB68 \| 8156RHZ6DZDLTDXWN816 \| F-LU-08 \| S19 | Arrangement ended on 2023-04-30 but no termination reason is reported |
| error | `BUS-002` | B_02.02 / row 86 / c0090 | AR-DE-0064 \| 3912RO6DCAXX71K9W972 \| 9845TQAG2OMFUSPMDI73 \| F-DE-11 \| S19 | Arrangement ended on 2025-10-31 but no termination reason is reported |
| error | `XRF-003` | B_02.02 / row 154 / c0030 | AR-DE-9001 \| 8156AYQ5YUFTZEC92R45 \| 8156YII8DXJIQ6LZZ583 \| F-AT-07 \| S10 | Provider '8156YII8DXJIQ6LZZ583' is not listed in B_05.01 |
| error | `FLD-002` | B_03.01 / row 11 / c0020 | CO-LU-0008 \|  | c0020 'LEI of the entity signing the contractual arrangement': '6354ZX2X914MZGYMMB99' is not a valid LEI: LEI checksum (ISO 17442 / MOD 97-10) failed; expected check digits 68 |
| error | `XRF-001` | B_04.01 / row 147 / c0010 | AR-AT-0000 \| 8156AYQ5YUFTZEC92R45 \|  | Contractual arrangement 'AR-AT-0000' is not reported in B_02.01 |
| error | `SC-003` | B_05.02 / row 6 / c0060 | MSA-DE-0001 \| S17 \| 5299KSAC8PGOY2WZG688 \| 3 \| 7245LHPDBFHF0V7L0532 | In 'MSA-DE-0001', recipient '7245LHPDBFHF0V7L0532' of rank 3 subcontractor '5299KSAC8PGOY2WZG688' is not reported at rank 2 |
| error | `SC-001` | B_05.02 / row 7 / c0030 | CO-LU-0002 \| S17 \| 6354222DLTFK714K9K18 \| 1 \|  | Rank 1 provider '6354222DLTFK714K9K18' is not a direct provider of 'CO-LU-0002' (expected one of: 5299XGE5RGK9SNVGG353) |
| error | `SC-003` | B_05.02 / row 8 / c0060 | CO-LU-0002 \| S17 \| 3912HE4IZZF3ZD1EDH65 \| 2 \| 5299XGE5RGK9SNVGG353 | In 'CO-LU-0002', recipient '5299XGE5RGK9SNVGG353' of rank 2 subcontractor '3912HE4IZZF3ZD1EDH65' is not reported at rank 1 |
| error | `BUS-015` | B_06.01 / row 22 / c0080 | F-LU-05 \| 6354ZX2X914MZGYMMB68 | Critical function 'F-LU-05' is missing Recovery time objective of the function (hours) |
| error | `BUS-019` | B_07.01 / row 6 / c0080 | CO-AT-0003 \| 5299XGE5RGK9SNVGG353 \| S17 | 'CO-AT-0003' supports critical function 'F-AT-01' but has no exit plan |
| error | `BUS-019` | B_07.01 / row 7 / c0080 | MSA-DE-0004 \| 5299XGE5RGK9SNVGG353 \| S18 | 'MSA-DE-0004' supports critical function 'F-DE-03' but has no exit plan |
| error | `XRF-013` | B_07.01 / row 20 / c0010 | AR-DE-0019 \| 21381VQL0Y482P2BV956 \| S03 | No B_02.02 row for arrangement 'AR-DE-0019', provider '21381VQL0Y482P2BV956', service S03 |
| error | `BUS-020` | B_07.01 / row 22 / c0060 | AR-DE-0022 \| 81567Y1C50614Y00S578 \| S13 | Substitutability is 'Not substitutable' but no reason is given |
| error | `XRF-013` | B_07.01 / row 50 / c0010 | AR-LU-0050 \| 8945J54J0JEU0CJ1E554 \| S19 | No B_02.02 row for arrangement 'AR-LU-0050', provider '8945J54J0JEU0CJ1E554', service S19 |
| warning | `BUS-008` | B_02.01 / row 19 / c0040 | AR-LU-0016 | Amount reported in CHF, reporting currency is EUR |
| warning | `XRF-008` | B_02.02 / row 38 / c0030 | AR-DE-0019 \| 3912RO6DCAXX71K9W972 \| 21381VQL0Y482P2BV900 \| F-DE-14 \| S03 | Provider '21381VQL0Y482P2BV900' of 'AR-DE-0019' is not reported in B_03.02 |
| warning | `XRF-008` | B_02.02 / row 154 / c0030 | AR-DE-9001 \| 8156AYQ5YUFTZEC92R45 \| 8156YII8DXJIQ6LZZ583 \| F-AT-07 \| S10 | Provider '8156YII8DXJIQ6LZZ583' of 'AR-DE-9001' is not reported in B_03.02 |
| warning | `XRF-010` | B_05.01 / row 49 / c0010 | 2138QO7IUC1RRV1FDZ58 | Provider '2138QO7IUC1RRV1FDZ58' (Legacy Mainframe Services GmbH) is not referenced by any arrangement or supply chain |
| warning | `BUS-016` | B_06.01 / row 33 / c0050 | F-AT-06 \| 8156AYQ5YUFTZEC92R45 | Function 'F-AT-06' has not been assessed |
| info | `XRF-014` | B_01.02 / row 4 / c0060 | 3912RO6DCAXX71K9W972 | Parent '5299NRPC2H5F3BPYBP79' of Alpenrand Bank (Europe) AG is not listed in B_01.02 |

---
_Not an official EBA/ESA tool; see docs/ASSUMPTIONS.md._
