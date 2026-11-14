"""Untyped intermediate representation produced by all importers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from dora_roi.validation.findings import Finding

RawValue = str | int | float | bool | date | datetime | Decimal | None


@dataclass
class RawRow:
    """One data row: column code → raw cell value, plus the 1-based source row number."""

    row: int | None
    values: dict[str, RawValue]


@dataclass
class RawTable:
    """Rows of one template as read from a sheet or CSV file."""

    template: str
    columns: list[str]
    rows: list[RawRow] = field(default_factory=list)
    source: str | None = None


@dataclass
class RawRegister:
    """All tables read from an input, plus import-level findings."""

    tables: dict[str, RawTable] = field(default_factory=dict)
    source: str | None = None
    findings: list[Finding] = field(default_factory=list)
