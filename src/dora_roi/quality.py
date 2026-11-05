"""Overall data-quality score of a register (0–100) and submission readiness.

Definition (``docs/DECISIONS.md`` D-026): each record scores 1 if it has no finding, 0.5 if it
only has warnings and 0 if it has at least one error; the score is the average × 100, rounded
down. Register-level errors (e.g. an empty core template) cap the score at 50. The register is
*ready* only when there is no error at all, whatever the score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from dora_roi.validation import Severity, ValidationReport


class Readiness(StrEnum):
    READY = "ready"
    ALMOST = "almost"
    NOT_READY = "not_ready"
    EMPTY = "empty"


@dataclass(frozen=True)
class QualityScore:
    score: int
    readiness: Readiness
    records: int
    records_with_errors: int
    records_with_warnings_only: int
    errors: int
    warnings: int


def quality_score(report: ValidationReport, almost_threshold: int = 10) -> QualityScore:
    records = sum(report.record_counts.values())
    worst: dict[tuple[str, object], Severity] = {}
    register_level_error = False
    for f in report.findings:
        if f.template is None or (f.row is None and f.record_key is None):
            if f.severity is Severity.ERROR:
                register_level_error = True
            continue
        key = (f.template, f.row if f.row is not None else f.record_key)
        current = worst.get(key)
        if current is None or f.severity.rank < current.rank:
            worst[key] = f.severity
    err = sum(1 for s in worst.values() if s is Severity.ERROR)
    warn = sum(1 for s in worst.values() if s is Severity.WARNING)
    counts = report.severity_counts()
    if records == 0:
        return QualityScore(0, Readiness.EMPTY, 0, 0, 0, counts["error"], counts["warning"])
    err = min(err, records)
    warn = min(warn, records - err)
    score = math.floor(100 * (records - err - 0.5 * warn) / records)
    if register_level_error:
        score = min(score, 50)
    if counts["error"] == 0:
        readiness = Readiness.READY
    elif counts["error"] <= almost_threshold:
        readiness = Readiness.ALMOST
    else:
        readiness = Readiness.NOT_READY
    return QualityScore(max(score, 0), readiness, records, err, warn, counts["error"],
                        counts["warning"])
