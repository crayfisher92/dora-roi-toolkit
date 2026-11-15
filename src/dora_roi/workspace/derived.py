"""Derived state of a workspace: incremental parsing, validation and accepted findings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dora_roi.io.parse import parse_row
from dora_roi.io.raw import RawRegister
from dora_roi.model import TEMPLATES_BY_CODE, RegisterOfInformation, RoIRecord
from dora_roi.validation import Finding, Severity, ValidationReport, finding_key
from dora_roi.workspace.history import Acceptance

ParseKey = tuple[str, int | None, tuple[tuple[str, Any], ...]]


@dataclass
class Derived:
    register: RegisterOfInformation
    report: ValidationReport


class Parser:
    """Parses raw tables into a typed register, re-using rows whose values did not change –
    an edit costs one row parse (``docs/BACKLOG.md`` B-08)."""

    def __init__(self) -> None:
        self._cache: dict[ParseKey, tuple[RoIRecord, list[Finding]]] = {}

    def parse(self, raw: RawRegister) -> tuple[RegisterOfInformation, list[Finding]]:
        register = RegisterOfInformation()
        findings: list[Finding] = list(raw.findings)
        cache: dict[ParseKey, tuple[RoIRecord, list[Finding]]] = {}
        for code, table in raw.tables.items():
            model = TEMPLATES_BY_CODE[code]
            source = table.source or raw.source
            for row in table.rows:
                key: ParseKey = (code, row.row, tuple(sorted(row.values.items())))
                hit = self._cache.get(key)
                if hit is None:
                    hit = parse_row(model, row, source)
                cache[key] = hit
                register.add(hit[0])
                findings.extend(hit[1])
        self._cache = cache
        return register, findings


def apply_acceptances(report: ValidationReport, acceptances: dict[str, Acceptance]
                      ) -> list[Acceptance]:
    """Move accepted warning/info findings to ``report.accepted``; return the acceptances
    whose finding is gone (resolved, or the record changed)."""
    if not acceptances:
        return []
    open_: list[Finding] = []
    matched: set[str] = set()
    for f in report.findings:
        key = finding_key(f)
        acc = acceptances.get(key)
        if acc is not None and f.severity is not Severity.ERROR:
            report.accepted.append(f.model_copy(update={"accepted_reason": acc.reason}))
            matched.add(key)
        else:
            open_.append(f)
    report.findings = open_
    return [acc for key, acc in acceptances.items() if key not in matched]
