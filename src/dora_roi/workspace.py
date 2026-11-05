"""An editable register: raw cell values as source of truth, re-validated after every change.

* The raw values (exactly what the user typed, including invalid ones) stay visible and
  editable; the typed register, validation report and analysis are derived on demand.
* Re-parsing is incremental: rows whose values did not change are taken from a cache, so an
  edit costs one row parse plus one validation run (``docs/BACKLOG.md`` B-08).
* Every change is an :class:`Change` in an append-only log (who, when, old → new) – the audit
  trail – and versions are positions in that log, so older states are reconstructed by
  undoing changes instead of storing full copies.
* Warnings and info findings can be *accepted* with a justification (:meth:`accept`);
  errors cannot, because they would make the supervisory submission fail.
* All mutations are serialised by a re-entrant lock (B-09).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dora_roi.analytics import ConcentrationAnalysis, analyse
from dora_roi.contracts.analysis import Portfolio, evaluate
from dora_roi.contracts.model import AssessmentBook
from dora_roi.incidents.model import IncidentLog
from dora_roi.io.parse import parse_raw, parse_row
from dora_roi.io.raw import RawRegister, RawRow, RawTable, RawValue
from dora_roi.model import TEMPLATE_MODELS, TEMPLATES_BY_CODE, RegisterOfInformation, RoIRecord
from dora_roi.quality import QualityScore, quality_score
from dora_roi.validation import (
    Finding,
    Severity,
    ValidationConfig,
    ValidationReport,
    finding_key,
    validate,
)

MAX_VERSIONS = 200
DEFAULT_USER = "local user"


class EditError(ValueError):
    """Raised for an edit that does not address an existing template/row/column."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Change:
    """One entry of the audit trail."""

    kind: str  # "set" | "add" | "delete" | "accept" | "unaccept"
    template: str
    row: int
    column: str | None
    old: RawValue
    new: RawValue
    at: datetime = field(default_factory=_now)
    user: str = DEFAULT_USER
    note: str = ""
    values: tuple[tuple[str, RawValue], ...] = ()  # full row for add/delete
    index: int = -1  # position of a deleted row


@dataclass
class Version:
    number: int
    label: str
    change_count: int
    errors: int
    warnings: int
    created: datetime = field(default_factory=_now)
    user: str = DEFAULT_USER


@dataclass(frozen=True)
class Acceptance:
    """A warning/info finding accepted with a justification."""

    key: str
    rule_id: str
    reason: str
    user: str
    at: datetime


@dataclass
class _Derived:
    register: RegisterOfInformation
    report: ValidationReport


ParseKey = tuple[str, int | None, tuple[tuple[str, Any], ...]]


def _ensure_all_tables(raw: RawRegister) -> None:
    for model in TEMPLATE_MODELS:
        if model.TEMPLATE not in raw.tables:
            raw.tables[model.TEMPLATE] = RawTable(model.TEMPLATE,
                                                  [c.code for c in model.columns()])


class Workspace:
    """A named, versioned, editable register."""

    def __init__(self, name: str, raw: RawRegister, *, source: str | None = None,
                 config: ValidationConfig | None = None, workspace_id: str | None = None,
                 kind: str = "upload", user: str = DEFAULT_USER) -> None:
        self.id = workspace_id or uuid.uuid4().hex
        self.name = name
        self.source = source or name
        self.kind = kind
        self.config = config or ValidationConfig()
        self.raw = raw
        _ensure_all_tables(self.raw)
        self.created = _now()
        self.changes: list[Change] = []
        self.versions: list[Version] = []
        self.acceptances: dict[str, Acceptance] = {}
        self.visited: set[str] = set()
        self.import_notes: list[str] | None = None
        #: DORA Art. 30 contract assessments, keyed by B_02.01 arrangement reference.
        self.contracts = AssessmentBook()
        #: ICT-related incidents with their classification answers and reporting history.
        self.incidents = IncidentLog()
        #: Browser session that owns the workspace in the web app (``""`` elsewhere).
        self.owner: str = ""
        #: Called after every change (used for autosaving project files).
        self.on_change: Callable[[Workspace], None] | None = None
        #: Where the workspace is autosaved, if anywhere.
        self.project_path: Path | None = None
        self.lock = threading.RLock()
        self._derived: _Derived | None = None
        self._analysis: ConcentrationAnalysis | None = None
        self._portfolio: Portfolio | None = None
        self._parse_cache: dict[ParseKey, tuple[RoIRecord, list[Finding]]] = {}
        self._row_index: dict[str, dict[int, RawRow]] = {}
        self.snapshot("Imported", user=user)

    def row_count(self) -> int:
        """Rows in all templates (a proxy for the workspace's memory footprint)."""
        return sum(len(t.rows) for t in self.raw.tables.values())

    # ------------------------------------------------------------------ derived state

    def _parse(self) -> tuple[RegisterOfInformation, list[Finding]]:
        register = RegisterOfInformation()
        findings: list[Finding] = list(self.raw.findings)
        cache: dict[ParseKey, tuple[RoIRecord, list[Finding]]] = {}
        for code, table in self.raw.tables.items():
            model = TEMPLATES_BY_CODE[code]
            source = table.source or self.raw.source
            for row in table.rows:
                key: ParseKey = (code, row.row, tuple(sorted(row.values.items())))
                hit = self._parse_cache.get(key)
                if hit is None:
                    hit = parse_row(model, row, source)
                cache[key] = hit
                register.add(hit[0])
                findings.extend(hit[1])
        self._parse_cache = cache
        return register, findings

    def _derive(self) -> _Derived:
        with self.lock:
            if self._derived is None:
                register, parse_findings = self._parse()
                report = validate(register, parse_findings=parse_findings, config=self.config,
                                  source=self.source)
                self._apply_acceptances(report)
                self._derived = _Derived(register, report)
            return self._derived

    def _apply_acceptances(self, report: ValidationReport) -> None:
        if not self.acceptances:
            return
        open_: list[Finding] = []
        matched: set[str] = set()
        for f in report.findings:
            key = finding_key(f)
            acc = self.acceptances.get(key)
            if acc is not None and f.severity is not Severity.ERROR:
                report.accepted.append(f.model_copy(update={"accepted_reason": acc.reason}))
                matched.add(key)
            else:
                open_.append(f)
        report.findings = open_
        for key in set(self.acceptances) - matched:  # finding resolved or record changed
            acc = self.acceptances.pop(key)
            self.changes.append(Change("unaccept", "register", 0, None, None, None,
                                       user=acc.user, note=f"{acc.rule_id}: acceptance "
                                       "expired – finding no longer present"))

    def _invalidate(self) -> None:
        self._derived = None
        self._analysis = None
        self._portfolio = None
        self._row_index = {}

    @property
    def register(self) -> RegisterOfInformation:
        return self._derive().register

    @property
    def report(self) -> ValidationReport:
        return self._derive().report

    @property
    def analysis(self) -> ConcentrationAnalysis:
        with self.lock:
            if self._analysis is None:
                self._analysis = analyse(self.register)
            return self._analysis

    @property
    def quality(self) -> QualityScore:
        return quality_score(self.report)

    @property
    def portfolio(self) -> Portfolio:
        """Art. 30 compliance of every arrangement (cached until the register or the
        assessments change – :meth:`programme_changed`)."""
        with self.lock:
            if self._portfolio is None:
                self._portfolio = evaluate(self.register, self.contracts)
            return self._portfolio

    def replace_programme(self, contracts: AssessmentBook | None = None,
                          incidents: IncidentLog | None = None) -> None:
        """Replace the programme data wholesale (sample loading, opening a project)."""
        with self.lock:
            if contracts is not None:
                self.contracts = contracts
            if incidents is not None:
                self.incidents = incidents
            self._portfolio = None

    def programme_changed(self, kind: str, subject: str, summary: str,
                          user: str = DEFAULT_USER) -> None:
        """Record a change of the DORA programme data in the audit trail and autosave.

        ``kind`` is ``"art30"`` (contract assessments) or ``"incident"`` (incident log);
        ``subject`` the arrangement reference or incident id. Callers hold :attr:`lock`
        while mutating :attr:`contracts` / :attr:`incidents`.
        """
        area = {"art30": "Art. 30", "incident": "Incidents"}.get(kind, kind)
        with self.lock:
            self.changes.append(Change(kind, area, 0, subject[:200] or None, None, None,
                                       user=user, note=summary[:500]))
            self._portfolio = None
            self._changed()

    # ------------------------------------------------------------------ access

    def table(self, template: str) -> RawTable:
        if template not in self.raw.tables:
            raise EditError(f"unknown template {template!r}")
        return self.raw.tables[template]

    def row(self, template: str, row: int) -> RawRow:
        table = self.table(template)
        index = self._row_index.get(template)
        if index is None:
            index = {r.row: r for r in table.rows if r.row is not None}
            self._row_index[template] = index
        found = index.get(row)
        if found is None:
            raise EditError(f"{template} has no row {row}")
        return found

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

    def _set(self, template: str, row: int, column: str, value: RawValue, user: str,
             note: str = "") -> Change | None:
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
        change = Change("set", template, row, column, old, new, user=user, note=note)
        self.changes.append(change)
        return change

    def edit(self, template: str, row: int, column: str, value: RawValue,
             user: str = DEFAULT_USER) -> Change | None:
        """Set one cell and re-validate. Returns ``None`` when nothing changed."""
        with self.lock:
            self._check_column(template, column)
            change = self._set(template, row, column, value, user)
            if change is not None:
                self._invalidate()
                self.snapshot(f"Edited {template} row {row} {column}", user=user)
            return change

    def bulk_replace(self, template: str, column: str, old: str, new: str,
                     rows: list[int] | None = None, user: str = DEFAULT_USER) -> int:
        """Replace every occurrence of ``old`` in a column (optionally only in ``rows``)."""
        with self.lock:
            self._check_column(template, column)
            count = 0
            wanted = set(rows) if rows is not None else None
            note = f"bulk: '{old}' → '{new}'"
            for r in self.table(template).rows:
                if wanted is not None and r.row not in wanted:
                    continue
                current = r.values.get(column)
                current_text = "" if current is None else str(current).strip()
                if current_text == old.strip() and r.row is not None and \
                        self._set(template, r.row, column, new, user, note) is not None:
                    count += 1
            if count:
                self._invalidate()
                self.snapshot(f"Replaced '{old}' with '{new}' in {template} {column} "
                              f"({count}×)", user=user)
            return count

    def add_row(self, template: str, values: dict[str, RawValue] | None = None,
                user: str = DEFAULT_USER) -> int:
        with self.lock:
            table = self.table(template)
            number = max((r.row or 0 for r in table.rows), default=3) + 1
            row = RawRow(number, dict(values or {}))
            table.rows.append(row)
            self.changes.append(Change("add", template, number, None, None, None, user=user,
                                       values=tuple(row.values.items())))
            self._invalidate()
            self.snapshot(f"Added {template} row {number}", user=user)
            return number

    def delete_row(self, template: str, row: int, user: str = DEFAULT_USER) -> None:
        with self.lock:
            table = self.table(template)
            target = self.row(template, row)
            index = table.rows.index(target)
            table.rows.remove(target)
            self.changes.append(Change("delete", template, row, None, None, None, user=user,
                                       values=tuple(target.values.items()), index=index))
            self._invalidate()
            self.snapshot(f"Deleted {template} row {row}", user=user)

    # ------------------------------------------------------------------ acceptance

    def accept(self, finding: Finding, reason: str, user: str = DEFAULT_USER) -> Acceptance:
        """Accept a warning or info finding with a justification (errors cannot be accepted)."""
        if finding.severity is Severity.ERROR:
            raise EditError("errors cannot be accepted; they must be fixed")
        if not reason.strip():
            raise EditError("a justification is required")
        with self.lock:
            key = finding_key(finding)
            acc = Acceptance(key, finding.rule_id, reason.strip(), user, _now())
            self.acceptances[key] = acc
            self.changes.append(Change("accept", finding.template or "register",
                                       finding.row or 0, finding.column, None, None,
                                       user=user, note=f"{finding.rule_id}: {acc.reason}"))
            self._invalidate()
            self._changed()
            return acc

    def unaccept(self, key: str, user: str = DEFAULT_USER) -> None:
        with self.lock:
            acc = self.acceptances.pop(key, None)
            if acc is None:
                raise EditError("no such accepted finding")
            self.changes.append(Change("unaccept", "register", 0, None, None, None, user=user,
                                       note=f"{acc.rule_id}: {acc.reason}"))
            self._invalidate()
            self._changed()

    # ------------------------------------------------------------------ versions

    def snapshot(self, label: str, user: str = DEFAULT_USER) -> Version:
        with self.lock:
            counts = self.report.severity_counts()
            number = self.versions[-1].number + 1 if self.versions else 1
            version = Version(number, label, len(self.changes), counts["error"],
                              counts["warning"], user=user)
            self.versions.append(version)
            if len(self.versions) > MAX_VERSIONS:
                del self.versions[1]  # keep the imported original
            self._changed()
            return version

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change(self)

    def version(self, number: int) -> Version:
        for v in self.versions:
            if v.number == number:
                return v
        raise EditError(f"no version {number}")

    def raw_at(self, number: int) -> RawRegister:
        """Reconstruct the raw register as it was at version ``number``."""
        with self.lock:
            target = self.version(number).change_count
            copy = RawRegister(source=self.raw.source, findings=list(self.raw.findings))
            for code, t in self.raw.tables.items():
                copy.tables[code] = RawTable(t.template, list(t.columns),
                                             [RawRow(r.row, dict(r.values)) for r in t.rows],
                                             source=t.source)
            for ch in reversed(self.changes[target:]):
                table = copy.tables.get(ch.template)
                if table is None:
                    continue
                if ch.kind == "set":
                    for r in table.rows:
                        if r.row == ch.row and ch.column:
                            r.values[ch.column] = ch.old
                elif ch.kind == "add":
                    table.rows = [r for r in table.rows if r.row != ch.row]
                elif ch.kind == "delete":
                    table.rows.insert(max(ch.index, 0), RawRow(ch.row, dict(ch.values)))
            return copy

    def register_at(self, number: int) -> RegisterOfInformation:
        return parse_raw(self.raw_at(number)).register

    # ------------------------------------------------------------------ export

    def export_register(self) -> RegisterOfInformation:
        """Register carrying the raw (possibly invalid) values, for writing files."""
        reg = RegisterOfInformation()
        with self.lock:
            for model in TEMPLATE_MODELS:
                for r in self.raw.tables[model.TEMPLATE].rows:
                    data = {spec.attr: r.values.get(spec.code) for spec in model.columns()}
                    reg.add(model.model_construct(None, **data))
        return reg
