"""Reporting timeline of a major ICT-related incident (initial, intermediate, final report).

Time limits (A-INC-04; Commission Delegated Regulation (EU) 2025/301, to be verified):

* **initial notification** – within 4 hours of classifying the incident as major, and no
  later than 24 hours after becoming aware of it;
* **intermediate report** – within 72 hours of submitting the initial notification;
* **final report** – within one month of the (latest) intermediate report.

Deadlines that depend on a report not yet submitted are *projected* from the previous
deadline. The optional weekend/bank-holiday relief of the RTS is deliberately **not**
applied: the earlier, conservative deadline is shown (A-INC-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from dora_roi.incidents.classify import Classification, add_months
from dora_roi.incidents.criteria import DEFAULT_THRESHOLDS, Thresholds
from dora_roi.incidents.model import Incident, ReportKind


class DeadlineState(StrEnum):
    DONE = "done"  # submitted on time
    LATE = "late"  # submitted after the deadline
    OVERDUE = "overdue"  # not submitted, deadline passed
    DUE = "due"  # not submitted, deadline ahead
    PROJECTED = "projected"  # depends on a previous report not yet submitted


@dataclass(frozen=True)
class Deadline:
    kind: ReportKind
    due: datetime
    basis: str  # machine key, translated by the UI ("classification+4h", …)
    submitted_at: datetime | None
    projected: bool

    def state(self, now: datetime) -> DeadlineState:
        if self.submitted_at is not None:
            return DeadlineState.DONE if self.submitted_at <= self.due else DeadlineState.LATE
        if now > self.due:
            return DeadlineState.OVERDUE
        return DeadlineState.PROJECTED if self.projected else DeadlineState.DUE

    def remaining(self, now: datetime) -> timedelta:
        return self.due - now


def timeline(incident: Incident, classification: Classification, now: datetime,
             th: Thresholds = DEFAULT_THRESHOLDS) -> list[Deadline]:
    """The three reporting deadlines – empty unless the incident is (classified) major."""
    if not classification.major:
        return []
    classified = incident.classified_at or now
    by_class = classified + timedelta(hours=th.initial_after_classification_hours)
    by_aware = incident.detected_at + timedelta(hours=th.initial_after_awareness_hours)
    initial_due, basis = ((by_class, "classification") if by_class <= by_aware
                          else (by_aware, "awareness"))
    initial = Deadline(ReportKind.INITIAL, initial_due, basis, incident.initial_submitted_at,
                       False)
    base = incident.initial_submitted_at or initial_due
    intermediate = Deadline(
        ReportKind.INTERMEDIATE, base + timedelta(hours=th.intermediate_after_initial_hours),
        "initial", incident.intermediate_submitted_at, incident.initial_submitted_at is None)
    base = incident.intermediate_submitted_at or intermediate.due
    final = Deadline(ReportKind.FINAL, add_months(base, th.final_after_intermediate_months),
                     "intermediate", incident.final_submitted_at,
                     incident.intermediate_submitted_at is None)
    return [initial, intermediate, final]


def next_deadline(deadlines: list[Deadline]) -> Deadline | None:
    """The first deadline not yet met (overdue or upcoming)."""
    return next((d for d in deadlines if d.submitted_at is None), None)


def humanise(delta: timedelta, lang: str = "en") -> str:
    """``2 d 3 h``, ``3 h 12 min``, ``45 min`` (absolute value)."""
    seconds = abs(int(delta.total_seconds()))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    d = "T" if lang == "de" else "d"
    if days:
        return f"{days} {d} {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"
