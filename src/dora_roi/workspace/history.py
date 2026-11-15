"""The audit trail: changes, versions and acceptances, and undoing changes on raw data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from dora_roi.io.raw import RawRegister, RawRow, RawTable, RawValue

MAX_VERSIONS = 200
DEFAULT_USER = "local user"


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


def undo(raw: RawRegister, changes: list[Change]) -> RawRegister:
    """A copy of ``raw`` with ``changes`` (the most recent ones) undone, newest first."""
    copy = RawRegister(source=raw.source, findings=list(raw.findings))
    for code, t in raw.tables.items():
        copy.tables[code] = RawTable(t.template, list(t.columns),
                                     [RawRow(r.row, dict(r.values)) for r in t.rows],
                                     source=t.source)
    for ch in reversed(changes):
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
