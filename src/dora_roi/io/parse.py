"""Convert a :class:`RawRegister` into a typed :class:`RegisterOfInformation`.

Field-level format problems are turned into findings (rules ``FLD-002`` … ``FLD-009``) and the
offending values are dropped so the rest of the row is still available to cross-template
checks (see ``docs/DECISIONS.md`` D-003).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from dora_roi.io.raw import RawRegister, RawRow
from dora_roi.model import TEMPLATES_BY_CODE, RegisterOfInformation, RoIRecord
from dora_roi.validation.field_rules import DEFAULT_FORMAT_RULE, PYDANTIC_ERROR_RULES
from dora_roi.validation.findings import RULES, Category, Finding


@dataclass
class ParseResult:
    register: RegisterOfInformation
    findings: list[Finding] = field(default_factory=list)


def _format_finding(
    model: type[RoIRecord], error: dict[str, Any], row: RawRow, source: str | None
) -> Finding:
    attr = str(error["loc"][0]) if error.get("loc") else ""
    spec = model.column(attr) if attr in model.model_fields else None
    rule_id = PYDANTIC_ERROR_RULES.get(str(error["type"]), DEFAULT_FORMAT_RULE)
    label = f"{spec.code} '{spec.label}'" if spec else attr
    raw_value = error.get("input")
    return Finding(
        rule_id=rule_id,
        severity=RULES[rule_id].severity,
        category=Category.FIELD,
        message=f"{label}: {error['msg']}",
        template=model.TEMPLATE,
        row=row.row,
        column=spec.code if spec else None,
        value=None if raw_value is None else str(raw_value),
        source=source,
    )


def parse_row(
    model: type[RoIRecord], row: RawRow, source: str | None = None
) -> tuple[RoIRecord, list[Finding]]:
    """Parse one raw row; never raises for data problems."""
    data: dict[str, Any] = {}
    for spec in model.columns():
        if spec.code in row.values:
            data[spec.attr] = row.values[spec.code]
    findings: list[Finding] = []
    invalid: set[str] = set()
    try:
        record = model.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            finding = _format_finding(model, dict(err), row, source)
            findings.append(finding)
            if err.get("loc"):
                invalid.add(str(err["loc"][0]))
        cleaned = {k: v for k, v in data.items() if k not in invalid}
        record = model.model_validate(cleaned)
    record.set_provenance(row.row, source, frozenset(invalid))
    key = record.key_str()
    for f in findings:
        f.record_key = key
    return record, findings


def parse_raw(raw: RawRegister) -> ParseResult:
    """Parse every table of ``raw`` into a typed register."""
    register = RegisterOfInformation()
    findings: list[Finding] = list(raw.findings)
    for code, table in raw.tables.items():
        model = TEMPLATES_BY_CODE[code]
        for row in table.rows:
            record, row_findings = parse_row(model, row, table.source or raw.source)
            register.add(record)
            findings.extend(row_findings)
    return ParseResult(register, findings)
