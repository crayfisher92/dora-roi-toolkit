"""An editable register: raw cell values as source of truth, re-validated after every change.

The raw values (exactly what the user typed, including invalid ones) are kept so that a
wrong value stays visible and editable; the typed register, the validation report and the
analysis are derived from them on demand. Every change creates a version so that versions
can be compared (``dora_roi.diff``).
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property

from dora_roi.analytics import ConcentrationAnalysis, analyse
from dora_roi.io.parse import parse_raw
from dora_roi.io.raw import RawRegister, RawRow, RawTable, RawValue
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE, RegisterOfInformation, RoIRecord
from dora_roi.quality import QualityScore, quality_score
from dora_roi.validation import Finding, ValidationConfig, ValidationReport, validate

MAX_VERSIONS = 50


class EditError(ValueError):
    """Raised for an edit that does not address an existing template/row/column."""


@dataclass(frozen=True)
class Change:
    template: str
    row: int
    column: str
    old: RawValue
    new: RawValue


@dataclass
class Version:
    number: int
    label: str
    raw: RawRegister
    errors: int
    warnings: int
    created: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _Derived:
    register: RegisterOfInformation
    report: ValidationReport


def _ensure_all_tables(raw: RawRegister) -> None:
    for model in TEMPLATE_MODELS:
        if model.TEMPLATE not in raw.tables:
            raw.tables[model.TEMPLATE] = RawTable(model.TEMPLATE,
                                                  [c.code for c in model.columns()])


class Workspace:
    """A named, versioned, editable register."""

    def __init__(self, name: str, raw: RawRegister, *, source: str | None = None,
                 config: ValidationConfig | None = None, workspace_id: str | None = None,
                 kind: str = "upload") -> None:
        self.id = workspace_id or uuid.uuid4().hex[:12]
        self.name = name
        self.source = source or name
        self.kind = kind
        self.config = config or ValidationConfig()
        self.raw = raw
        _ensure_all_tables(self.raw)
        self.created = datetime.now(UTC)
        self.changes: list[Change] = []
        self.versions: list[Version] = []
        self.visited: set[str] = set()
        self._derived: _Derived | None = None
        self.snapshot("Imported")

    # ------------------------------------------------------------------ derived state

    def _derive(self) -> _Derived:
        if self._derived is None:
            parsed = parse_raw(self.raw)
            report = validate(parsed.register, parse_findings=parsed.findings,
                              config=self.config, source=self.source)
            self._derived = _Derived(parsed.register, report)
        return self._derived

    def _invalidate(self) -> None:
        self._derived = None
        self.__dict__.pop("analysis", None)

    @property
    def register(self) -> RegisterOfInformation:
        return self._derive().register

    @property
    def report(self) -> ValidationReport:
        return self._derive().report

    @cached_property
    def analysis(self) -> ConcentrationAnalysis:
        return analyse(self.register)

    @property
    def quality(self) -> QualityScore:
        return quality_score(self.report)

    # ------------------------------------------------------------------ access

    def table(self, template: str) -> RawTable:
        if template not in self.raw.tables:
            raise EditError(f"unknown template {template!r}")
        return self.raw.tables[template]

    def row(self, template: str, row: int) -> RawRow:
        for r in self.table(template).rows:
            if r.row == row:
                return r
        raise EditError(f"{template} has no row {row}")

    def record(self, template: str, row: int) -> RoIRecord | None:
        for rec in self.register.records(template):
            if rec.row == row:
                return rec
        return None

    def findings_for(self, template: str, row: int) -> list[Finding]:
        return [f for f in self.report.findings if f.template == template and f.row == row]

    def rows_with_findings(self, template: str) -> dict[int, list[Finding]]:
        out: dict[int, list[Finding]] = {}
        for f in self.report.findings:
            if f.template == template and f.row is not None:
                out.setdefault(f.row, []).append(f)
        return out

    # ------------------------------------------------------------------ editing

    def _check_column(self, template: str, column: str) -> None:
        if template not in TEMPLATES_BY_CODE:
            raise EditError(f"unknown template {template!r}")
        if TEMPLATES_BY_CODE[template].column_by_code(column) is None:
            raise EditError(f"{template} has no column {column!r}")

    def _set(self, template: str, row: int, column: str, value: RawValue) -> Change | None:
        target = self.row(template, row)
        old = target.values.get(column)
        new: RawValue = value.strip() if isinstance(value, str) else value
        if new == "":
            new = None
        if old == new:
            return None
        target.values[column] = new
        if column not in self.table(template).columns:
            self.table(template).columns.append(column)
        change = Change(template, row, column, old, new)
        self.changes.append(change)
        return change

    def edit(self, template: str, row: int, column: str, value: RawValue) -> Change | None:
        """Set one cell and re-validate. Returns ``None`` when nothing changed."""
        self._check_column(template, column)
        change = self._set(template, row, column, value)
        if change is not None:
            self._invalidate()
            self.snapshot(f"Edited {template} row {row} {column}")
        return change

    def bulk_replace(self, template: str, column: str, old: str, new: str,
                     rows: list[int] | None = None) -> int:
        """Replace every occurrence of ``old`` in a column (optionally only in ``rows``)."""
        self._check_column(template, column)
        count = 0
        wanted = set(rows) if rows is not None else None
        for r in self.table(template).rows:
            if wanted is not None and r.row not in wanted:
                continue
            current = r.values.get(column)
            current_text = "" if current is None else str(current).strip()
            if current_text == old.strip() and r.row is not None and \
                    self._set(template, r.row, column, new) is not None:
                count += 1
        if count:
            self._invalidate()
            self.snapshot(f"Replaced '{old}' with '{new}' in {template} {column} ({count}×)")
        return count

    def add_row(self, template: str, values: dict[str, RawValue] | None = None) -> int:
        table = self.table(template)
        number = max((r.row or 0 for r in table.rows), default=3) + 1
        table.rows.append(RawRow(number, dict(values or {})))
        self._invalidate()
        self.snapshot(f"Added {template} row {number}")
        return number

    def delete_row(self, template: str, row: int) -> None:
        table = self.table(template)
        target = self.row(template, row)
        table.rows.remove(target)
        self._invalidate()
        self.snapshot(f"Deleted {template} row {row}")

    # ------------------------------------------------------------------ versions

    def snapshot(self, label: str) -> Version:
        counts = self.report.severity_counts()
        version = Version(len(self.versions) + 1 if not self.versions
                          else self.versions[-1].number + 1, label, copy.deepcopy(self.raw),
                          counts["error"], counts["warning"])
        self.versions.append(version)
        if len(self.versions) > MAX_VERSIONS:
            del self.versions[1]  # keep the imported original
        return version

    def version(self, number: int) -> Version:
        for v in self.versions:
            if v.number == number:
                return v
        raise EditError(f"no version {number}")

    def register_at(self, number: int) -> RegisterOfInformation:
        return parse_raw(self.version(number).raw).register

    # ------------------------------------------------------------------ export

    def export_register(self) -> RegisterOfInformation:
        """Register carrying the raw (possibly invalid) values, for writing files."""
        reg = RegisterOfInformation()
        for model in TEMPLATE_MODELS:
            for r in self.raw.tables[model.TEMPLATE].rows:
                data = {spec.attr: r.values.get(spec.code) for spec in model.columns()}
                reg.add(model.model_construct(None, **data))
        return reg
