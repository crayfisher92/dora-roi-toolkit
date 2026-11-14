"""Import-level and field-level rules (IMP-*, FLD-*)."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterator

from dora_roi.lei import explain_lei_error, is_valid_lei
from dora_roi.model import TEMPLATE_MODELS, RoIRecord
from dora_roi.model.eba_codes import EBA_CURRENCIES, licensed_activity_code
from dora_roi.validation.context import ValidationContext
from dora_roi.validation.findings import Category, Finding, Severity, declare, rule

ALL = tuple(m.TEMPLATE for m in TEMPLATE_MODELS)
ANNEX = ("ITS Annex I", "ITS Annex II")

# ----------------------------------------------------------------------------- import rules

declare("IMP-001", "Unrecognised sheet or file ignored", severity=Severity.INFO,
        category=Category.IMPORT, templates=(), references=("ITS Annex I",),
        description="A sheet/file whose name does not match any RoI template was skipped.")
declare("IMP-002", "Template missing from input", severity=Severity.WARNING,
        category=Category.IMPORT, templates=ALL, references=("DORA Art. 28(3)", "ITS Annex I"),
        description="No sheet/file was found for a template; it is treated as empty.")
declare("IMP-003", "Unknown column ignored", severity=Severity.WARNING,
        category=Category.IMPORT, templates=ALL, references=("ITS Annex I",),
        description="A column header is not a column code of the template; values are ignored.")
declare("IMP-004", "Header row not found", severity=Severity.ERROR,
        category=Category.IMPORT, templates=ALL, references=("ITS Annex I",),
        description="No row of column codes (c0010, c0020, …) could be located in the sheet.")

# ----------------------------------------------------------------------------- format rules

declare("FLD-002", "Invalid LEI", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ISO 17442", "ITS Art. – identification"),
        description="LEI must be 20 alphanumeric characters with valid MOD 97-10 check digits.")
declare("FLD-003", "Invalid date", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ISO 8601", "ITS Annex II"),
        description="Dates must be valid calendar dates in ISO 8601 format YYYY-MM-DD.")
declare("FLD-004", "Value not in code list", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ITS Annex II", "ITS Annex III"),
        description="Closed-list columns only accept the values defined by the ITS.")
declare("FLD-005", "Invalid country code", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ISO 3166-1", "ITS Annex II", "DORA Art. 30(2)"),
        description="Countries must be ISO 3166-1 alpha-2 codes (e.g. GB, not UK).")
declare("FLD-006", "Invalid currency code", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ISO 4217", "ITS Annex II"),
        description="Currencies must be active ISO 4217 alphabetic codes.")
declare("FLD-007", "Invalid number", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ITS Annex II",),
        description="Monetary amounts, day counts, hours and ranks must be non-negative numbers "
        "of the expected type (integers where required).")
declare("FLD-008", "Invalid boolean", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ITS Annex II",),
        description="Yes/no columns must be true or false.")
declare("FLD-009", "Text too long", severity=Severity.ERROR, category=Category.FIELD,
        templates=ALL, references=("ITS Annex II", "EBA reporting"),
        description="Alphanumeric values are limited to 255 characters.")

PYDANTIC_ERROR_RULES: dict[str, str] = {
    "roi_lei": "FLD-002",
    "roi_date": "FLD-003",
    "roi_codelist": "FLD-004",
    "roi_country": "FLD-005",
    "roi_currency": "FLD-006",
    "roi_bool": "FLD-008",
    "string_too_long": "FLD-009",
}
DEFAULT_FORMAT_RULE = "FLD-007"


# ----------------------------------------------------------------------------- engine checks


@rule("FLD-001", "Mandatory value missing", severity=Severity.ERROR, category=Category.FIELD,
      templates=ALL, references=("DORA Art. 28(3)", *ANNEX),
      description="Every column flagged mandatory (M) in the ITS must be reported for each row.")
def check_mandatory(ctx: ValidationContext) -> Iterator[Finding]:
    for record in ctx.register.iter_all():
        invalid = record.invalid_fields
        for spec in record.columns():
            if not spec.col.mandatory or spec.attr in invalid:
                continue
            if getattr(record, spec.attr) is None:
                yield ctx.finding("FLD-001", f"Mandatory column {spec.code} '{spec.label}' is "
                                  "empty", record, spec.attr)


#: B_02.02 columns the ITS makes mandatory when the ICT service supports a critical or important
#: function (c0170 additionally needs storage of data and is checked by BUS-005).
CRITICAL_SERVICE_COLUMNS = ("notice_period_entity", "notice_period_provider",
                            "governing_law_country", "service_country", "data_storage",
                            "reliance_level")


@rule("FLD-014", "Conditionally mandatory value missing", severity=Severity.ERROR,
      category=Category.FIELD, templates=("B_01.02", "B_02.02", "B_05.01"),
      references=("DORA Art. 28(3)", *ANNEX),
      description="Columns the ITS makes mandatory under a condition: total assets of financial "
      "entities and their currency (B_01.02 c0110, c0100); notice periods, governing law, country "
      "of provision, storage of data and level of reliance of ICT services supporting critical "
      "or important functions (B_02.02 c0100-c0140, c0180); total annual expense of direct ICT "
      "third-party service providers and its currency (B_05.01 c0100, c0090).")
def check_conditional(ctx: ValidationContext) -> Iterator[Finding]:
    def missing(record: RoIRecord, attr: str, why: str) -> Iterator[Finding]:
        if getattr(record, attr) is None and attr not in record.invalid_fields:
            spec = type(record).column(attr)
            yield ctx.finding("FLD-014", f"Column {spec.code} '{spec.label}' is empty but "
                              f"required {why}", record, attr)

    for e in ctx.register.b_01_02:
        if e.entity_type is not None and e.entity_type.is_financial:
            yield from missing(e, "total_assets", "for a financial entity")
        if e.total_assets is not None:
            yield from missing(e, "currency", "because total assets are reported")
    for s in ctx.register.b_02_02:
        if ctx.supports_critical(s):
            for attr in CRITICAL_SERVICE_COLUMNS:
                yield from missing(s, attr, "because the ICT service supports a critical or "
                                   "important function")
    direct = {s.provider_code for s in ctx.register.b_02_02 if s.provider_code}
    for p in ctx.register.b_05_01:
        if p.provider_code in direct:
            yield from missing(p, "total_annual_cost", "for a direct ICT third-party service "
                               "provider")
        if p.total_annual_cost is not None:
            yield from missing(p, "currency", "because the total annual expense is reported")


def _key_present(record: RoIRecord) -> bool:
    return any(v is not None for v in record.key())


@rule("FLD-010", "Duplicate record key", severity=Severity.ERROR, category=Category.FIELD,
      templates=ALL, references=("ITS Annex II", "ITS Art. – consistency"),
      description="Each template has a primary key (e.g. the contractual arrangement reference "
      "number in B_02.01); the same key must not be reported twice.")
def check_duplicates(ctx: ValidationContext) -> Iterator[Finding]:
    for model in TEMPLATE_MODELS:
        seen: dict[tuple[object, ...], list[RoIRecord]] = defaultdict(list)
        for record in ctx.register.records(model.TEMPLATE):
            if _key_present(record):
                seen[record.key()].append(record)
        for records in seen.values():
            if len(records) < 2:
                continue
            first = records[0]
            for dup in records[1:]:
                where = f"row {first.row}" if first.row else "an earlier row"
                yield ctx.finding("FLD-010", f"Duplicate key ({', '.join(model.KEY)}) = "
                                  f"'{dup.key_str()}' already reported in {where}", dup)


@rule("FLD-011", "Single-row template with the wrong number of rows", severity=Severity.ERROR,
      category=Category.FIELD, templates=("B_01.01", "B_99.01"),
      references=("DORA Art. 28(3)", "ITS Annex I", "EBA reporting"),
      description="The register is maintained by exactly one entity, reported in B_01.01; the "
      "definitions of B_99.01 form a single row (a closed table of the data point model).")
def check_single_maintainer(ctx: ValidationContext) -> Iterator[Finding]:
    n = len(ctx.register.b_01_01)
    if n != 1:
        yield ctx.finding("FLD-011", f"B_01.01 contains {n} rows; exactly one is expected",
                          template="B_01.01")
    n = len(ctx.register.b_99_01)
    if n > 1:
        yield ctx.finding("FLD-011", f"B_99.01 contains {n} rows; at most one is expected",
                          template="B_99.01")


@rule("FLD-012", "Core template is empty", severity=Severity.ERROR, category=Category.FIELD,
      templates=("B_01.02", "B_02.01", "B_02.02", "B_05.01", "B_06.01"),
      references=("DORA Art. 28(3)", "ITS Annex I"),
      description="A register without entities, contracts, providers or functions cannot be "
      "submitted.")
def check_core_templates(ctx: ValidationContext) -> Iterator[Finding]:
    for code in ("B_01.02", "B_02.01", "B_02.02", "B_05.01", "B_06.01"):
        if not ctx.register.records(code):
            yield ctx.finding("FLD-012", f"Template {code} contains no rows", template=code)


EUID_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9][A-Z0-9.\-]{2,}$")


@rule("FLD-013", "Provider code inconsistent with its code type", severity=Severity.ERROR,
      category=Category.FIELD, templates=("B_02.02", "B_03.02", "B_05.01", "B_05.02", "B_07.01"),
      references=("ISO 17442", "ITS Art. – identification"),
      description="When the type of code is LEI the identification code must be a valid LEI; "
      "when it is EUID it must start with an ISO country code followed by the register "
      "identifier. Applies to provider, ultimate parent, recipient and additional codes.")
def check_provider_code_format(ctx: ValidationContext) -> Iterator[Finding]:
    pairs = (
        ("provider_code", "provider_code_type"),
        ("ultimate_parent_code", "ultimate_parent_code_type"),
        ("recipient_code", "recipient_code_type"),
        ("additional_code", "additional_code_type"),
    )
    for record in ctx.register.iter_all():
        for code_attr, type_attr in pairs:
            if code_attr not in type(record).model_fields:
                continue
            code = getattr(record, code_attr)
            code_type = getattr(record, type_attr)
            if code is None or code_type is None:
                continue
            if code_type.value == "LEI":
                problem = explain_lei_error(code)
                if problem:
                    yield ctx.finding("FLD-013", f"'{code}' is typed as LEI but {problem}",
                                      record, code_attr, value=code)
            elif is_valid_lei(code):
                yield ctx.finding("FLD-013", f"'{code}' is a valid LEI but its code type is "
                                  f"{code_type.value}; report the type as LEI", record,
                                  type_attr, value=code)
            elif code_type.value == "EUID" and not EUID_PATTERN.match(code):
                yield ctx.finding("FLD-013", f"'{code}' does not look like an EUID "
                                  "(country code + register + registration number)",
                                  record, code_attr, value=code)


@rule("FLD-015", "Value not in the EBA taxonomy list", severity=Severity.ERROR,
      category=Category.FIELD, templates=("B_01.02", "B_02.01", "B_05.01", "B_06.01"),
      references=("ITS Annex IV", "EBA reporting"),
      description="Closed lists of the EBA data point model that are narrower than the ISO "
      "standards: the licensed activity (B_06.01 c0020) must be an activity of the EBA list "
      "(ITS Annex IV) and currencies must be members of the DPM currency list, otherwise the "
      "authority rejects the value (EBA technical check 503).")
def check_dpm_lists(ctx: ValidationContext) -> Iterator[Finding]:
    for f in ctx.register.b_06_01:
        if f.licensed_activity and licensed_activity_code(f.licensed_activity) is None:
            yield ctx.finding("FLD-015", f"'{f.licensed_activity}' is not a licensed activity of "
                              "the EBA list (ITS Annex IV)", f, "licensed_activity",
                              value=f.licensed_activity)
    for record in ctx.register.iter_all():
        if "currency" in type(record).model_fields and "currency" not in record.invalid_fields:
            currency = getattr(record, "currency")  # noqa: B009
            if currency and currency not in EBA_CURRENCIES:
                yield ctx.finding("FLD-015", f"Currency {currency} is a valid ISO 4217 code but "
                                  "not a member of the EBA DPM 4.0 currency list", record,
                                  "currency", value=currency)
