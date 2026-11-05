# Design decisions

This log records judgement calls made while building the toolkit, so that reviewers can
challenge them explicitly. Regulatory *interpretations* (as opposed to engineering choices)
live in [`ASSUMPTIONS.md`](ASSUMPTIONS.md).

| ID | Decision | Rationale |
|----|----------|-----------|
| D-001 | Package `dora_roi` (src layout), CLI entry point `roi`, Python ≥ 3.11. | `StrEnum`, `Self` and modern typing; 3.11 is the oldest CPython still widely deployed in banks' managed environments. |
| D-002 | **All model fields are `Optional` at the type level.** Mandatory / conditional / optional requirements are declared as metadata (`Col(requirement=…)`) and enforced by the validation engine. | A register under construction is always incomplete. If Pydantic enforced mandatoriness, a single missing value would make the whole row unloadable and hide every other problem. Consultants need *all* findings in one run. |
| D-003 | Format checks (LEI checksum, ISO 3166 / ISO 4217 codes, ISO 8601 dates, code lists, ranges) are enforced by Pydantic annotated types raising `PydanticCustomError("roi_*")`. The parser maps these error types onto validation rule IDs (`FLD-*`). Invalid values are reported and then *discarded* (set to `None`) so the rest of the row still loads. | One source of truth for formats (usable programmatically: `ContractSpecific.model_validate(...)`), while still giving the validation engine full control over severities and reporting. The discarded attributes are tracked (`record.invalid_fields`) so that the mandatory-field rule does not double-report them. |
| D-004 | Column metadata is attached with `typing.Annotated[..., Col(...)]` on the model fields rather than in a separate schema file. | Keeps the typed model, the Excel template generator, the importers, the exporter and the documentation in sync from a single declaration. |
| D-005 | Code lists use **toolkit-internal stable codes** (e.g. `S19`, `CRITICAL`, `OVERARCHING`) with human labels; importers accept code, label, alias or an `eba_XX:` prefixed value case-insensitively. | The exact EBA taxonomy member names for many enumerations could not be verified offline (see A-CL-*). Internal codes decouple the data model from taxonomy releases; the xBRL-CSV exporter applies a configurable mapping. |
| D-006 | Reference data (249 ISO 3166-1 countries, ISO 4217 currencies, EU/EEA lists) is embedded, not pulled from `pycountry`. | Zero heavyweight dependencies, deterministic behaviour, easy to audit. |
| D-007 | Primary key of B_05.01 is the provider identification code alone (not code + code type). | LEI and EUID namespaces do not overlap syntactically; using the code alone makes cross-template look-ups simpler and catches the same provider being reported twice with different code types. |
| D-008 | Primary key of B_06.01 is (function identifier, entity LEI). | In a group register the same function identifier may legitimately be reused by different entities; B_02.02 carries both values so the composite key can be resolved. |
