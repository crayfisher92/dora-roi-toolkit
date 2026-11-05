"""Helpers shared by tabular importers (Excel and CSV)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from dora_roi.io.raw import RawRow, RawTable, RawValue
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE, RoIRecord
from dora_roi.model.types import Col, Kind
from dora_roi.validation.findings import RULES, Category, Finding

_TEMPLATE_RE = re.compile(r"^\s*b[\s_\-.]?(\d{2})[\s_\-.]?(\d{2})\s*$", re.IGNORECASE)
_CODE_RE = re.compile(r"^c\d{4}$", re.IGNORECASE)

KIND_HINTS: dict[Kind, str] = {
    Kind.TEXT: "Text (max 255)",
    Kind.LEI: "LEI (20 characters, ISO 17442)",
    Kind.PROVIDER_CODE: "LEI or EUID",
    Kind.COUNTRY: "Country (ISO 3166-1 alpha-2, e.g. DE)",
    Kind.CURRENCY: "Currency (ISO 4217, e.g. EUR)",
    Kind.DATE: "Date (YYYY-MM-DD)",
    Kind.BOOLEAN: "true / false",
    Kind.INTEGER: "Whole number ≥ 0",
    Kind.MONETARY: "Amount ≥ 0",
    Kind.CODELIST: "Code list",
}

REQUIREMENT_TEXT = {"M": "Mandatory", "C": "Conditional", "O": "Optional"}


def template_code_for(name: str) -> str | None:
    """Map a sheet or file name (``B_02.02``, ``b_02.02.csv``, ``B0202``) to a template code."""
    stem = re.sub(r"\.(csv|txt)$", "", name.strip(), flags=re.IGNORECASE)
    m = _TEMPLATE_RE.match(stem)
    if not m:
        return None
    code = f"B_{m.group(1)}.{m.group(2)}"
    return code if code in TEMPLATES_BY_CODE else None


def file_name_for(template: str) -> str:
    """xBRL-CSV style file name of a template (``b_02.02.csv``)."""
    return template.lower() + ".csv"


def column_hint(col: Col) -> str:
    """One-line hint shown under the label in generated templates."""
    hint = f"{REQUIREMENT_TEXT[col.requirement.value]} · {KIND_HINTS[col.kind]}"
    if col.codelist is not None:
        hint = f"{REQUIREMENT_TEXT[col.requirement.value]} · {col.codelist.__name__}: " + ", ".join(
            m.value for m in col.codelist
        )
    if col.condition:
        hint += f" · {col.condition}"
    return hint


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def header_mapping(model: type[RoIRecord], cells: Sequence[RawValue]) -> dict[int, str] | None:
    """Return ``{cell index: column code}`` if ``cells`` look like a header row."""
    by_label = {_norm(s.label): s.code for s in model.columns()}
    mapping: dict[int, str] = {}
    hits = 0
    for idx, cell in enumerate(cells):
        if cell is None or str(cell).strip() == "":
            continue
        text = str(cell).strip()
        if _CODE_RE.match(text):
            mapping[idx] = text.lower()
            hits += 1
        elif _norm(text) in by_label:
            mapping[idx] = by_label[_norm(text)]
            hits += 1
    return mapping if hits else None


def is_annotation_row(model: type[RoIRecord], mapping: dict[int, str],
                      cells: Sequence[RawValue]) -> bool:
    """True if the row only contains the generated label/hint texts (not data)."""
    texts: dict[str, set[str]] = {}
    for spec in model.columns():
        texts[spec.code] = {_norm(spec.label), _norm(column_hint(spec.col))}
    seen_any = False
    for idx, code in mapping.items():
        cell = cells[idx] if idx < len(cells) else None
        if cell is None or str(cell).strip() == "":
            continue
        seen_any = True
        if _norm(cell) not in texts.get(code, set()):
            return False
    return seen_any


def import_finding(rule_id: str, message: str, template: str | None = None,
                   source: str | None = None, column: str | None = None) -> Finding:
    rule = RULES[rule_id]
    return Finding(rule_id=rule_id, severity=rule.severity, category=Category.IMPORT,
                   message=message, template=template, source=source, column=column)


def build_table(
    template: str,
    rows: Iterable[tuple[int, Sequence[RawValue]]],
    source: str,
    findings: list[Finding],
) -> RawTable:
    """Turn sheet/CSV rows (row number, cells) into a :class:`RawTable`.

    Locates the header among the first 10 rows, skips label/hint rows produced by the template
    generator and blank rows, and reports unknown columns.
    """
    model = TEMPLATES_BY_CODE[template]
    known = {s.code for s in model.columns()}
    table = RawTable(template=template, columns=[], source=source)
    mapping: dict[int, str] | None = None
    in_header_block = False
    for row_no, cells in rows:
        if mapping is None:
            if row_no > 10:
                break
            mapping = header_mapping(model, cells)
            if mapping is not None:
                for code in sorted(set(mapping.values()) - known):
                    findings.append(import_finding(
                        "IMP-003", f"Column '{code}' is not part of {template}; ignored",
                        template, source, code))
                mapping = {i: c for i, c in mapping.items() if c in known}
                table.columns = list(mapping.values())
                in_header_block = True
            continue
        if in_header_block and is_annotation_row(model, mapping, cells):
            continue
        in_header_block = False
        values: dict[str, RawValue] = {}
        for idx, code in mapping.items():
            cell = cells[idx] if idx < len(cells) else None
            if isinstance(cell, str) and cell.strip() == "":
                cell = None
            values[code] = cell
        if all(v is None for v in values.values()):
            continue
        table.rows.append(RawRow(row=row_no, values=values))
    if mapping is None:
        findings.append(import_finding(
            "IMP-004", f"No header row with column codes (c0010 …) found for {template}",
            template, source))
    return table


def missing_template_findings(found: Iterable[str], source: str) -> list[Finding]:
    present = set(found)
    return [
        import_finding("IMP-002", f"Template {m.TEMPLATE} ({m.TITLE}) not found in input; "
                       "treated as empty", m.TEMPLATE, source)
        for m in TEMPLATE_MODELS
        if m.TEMPLATE not in present
    ]
