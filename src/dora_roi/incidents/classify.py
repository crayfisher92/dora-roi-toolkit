"""Classify an incident as major / not major, explain why, and find recurring incidents.

Unknown answers are handled with three-valued logic: a criterion is *met*, *not met* or
*unknown*. The outcome is computed twice – with every unknown taken as "not met" and as
"met" – and is definitive only when both agree. Otherwise it is **undetermined** and the open
questions that could change it are listed: the questionnaire then guides the user to what
still has to be established (A-INC-03).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from dora_roi.incidents.criteria import COUNTED, DEFAULT_THRESHOLDS, Criterion, Thresholds
from dora_roi.incidents.model import Answers, Incident, IncidentLog
from dora_roi.model.refdata import EEA_COUNTRIES


class Outcome(StrEnum):
    MAJOR = "major"
    NOT_MAJOR = "not_major"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class Trigger:
    """A sub-threshold that was met, with the observed value (machine- and human-readable)."""

    key: str  # e.g. "clients_share"
    value: str  # e.g. "14.6 %"
    limit: str  # e.g. "> 10 %"


@dataclass
class CriterionResult:
    criterion: Criterion
    met: bool | None
    triggers: list[Trigger] = field(default_factory=list)
    #: Answers still missing that could make the criterion met.
    open_questions: list[str] = field(default_factory=list)


@dataclass
class Classification:
    outcome: Outcome
    results: dict[Criterion, CriterionResult]
    malicious_access: bool | None
    met_count: int
    possible_count: int

    @property
    def major(self) -> bool:
        return self.outcome is Outcome.MAJOR

    @property
    def met(self) -> list[CriterionResult]:
        return [r for c, r in self.results.items() if c in COUNTED and r.met]

    @property
    def basis(self) -> str:
        """Short machine key of why the outcome was reached (translated by the UI)."""
        crit = self.results[Criterion.CRITICAL_SERVICES].met
        if self.outcome is Outcome.MAJOR:
            return "malicious" if self.malicious_access and self.met_count < 2 else "thresholds"
        if self.outcome is Outcome.NOT_MAJOR:
            return "no_critical" if crit is False else "below"
        return "open"

    @property
    def open_questions(self) -> list[str]:
        out: list[str] = []
        for r in self.results.values():
            for q in r.open_questions:
                if q not in out:
                    out.append(q)
        if self.outcome is Outcome.UNDETERMINED and self.malicious_access is None:
            out.append("malicious_access")
        return out


def _pct(v: float) -> str:
    return f"{v * 100:.1f} %"


def _share(affected: int | Decimal | None, total: int | Decimal | None) -> float | None:
    if affected is None or total is None or not total:
        return None
    return float(affected) / float(total)


def _any(values: list[bool | None]) -> bool | None:
    if any(v is True for v in values):
        return True
    if all(v is False for v in values):
        return False
    return None


def _clients(a: Answers, th: Thresholds) -> CriterionResult:
    r = CriterionResult(Criterion.CLIENTS, None)
    checks: list[bool | None] = []

    def check(key: str, value: float | None, limit: float, shown: str, lim: str,
              questions: tuple[str, ...]) -> None:
        if value is None:
            checks.append(None)
            r.open_questions.extend(q for q in questions if q not in r.open_questions)
            return
        hit = value > limit
        checks.append(hit)
        if hit:
            r.triggers.append(Trigger(key, shown, lim))

    s = _share(a.clients_affected, a.clients_total)
    check("clients_share", s, th.clients_share, _pct(s or 0), f"> {th.clients_share:.0%}",
          ("clients_affected", "clients_total"))
    n = a.clients_affected
    check("clients_absolute", None if n is None else float(n), th.clients_absolute,
          f"{n or 0:,}", f"> {th.clients_absolute:,}", ("clients_affected",))
    s = _share(a.counterparts_affected, a.counterparts_total)
    check("counterparts_share", s, th.counterparts_share, _pct(s or 0),
          f"> {th.counterparts_share:.0%}", ("counterparts_affected", "counterparts_total"))
    s = _share(a.transactions_affected, a.transactions_daily)
    check("transactions_share", s, th.transactions_share, _pct(s or 0),
          f"> {th.transactions_share:.0%}", ("transactions_affected", "transactions_daily"))
    s = _share(a.transaction_value_affected, a.transaction_value_daily)
    check("transaction_value_share", s, th.transaction_value_share, _pct(s or 0),
          f"> {th.transaction_value_share:.0%}",
          ("transaction_value_affected", "transaction_value_daily"))
    if a.relevant_clients is None:
        checks.append(None)
        r.open_questions.append("relevant_clients")
    else:
        checks.append(a.relevant_clients)
        if a.relevant_clients:
            r.triggers.append(Trigger("relevant_clients", "yes", "any"))
    r.met = _any(checks)
    if r.met:
        r.open_questions = []
    return r


def _bools(criterion: Criterion, pairs: list[tuple[str, bool | None]]) -> CriterionResult:
    r = CriterionResult(criterion, _any([v for _, v in pairs]))
    for key, value in pairs:
        if value:
            r.triggers.append(Trigger(key, "yes", "any"))
        elif value is None and r.met is not True:
            r.open_questions.append(key)
    return r


def _duration(incident: Incident | None, a: Answers, th: Thresholds,
              now: datetime | None) -> CriterionResult:
    r = CriterionResult(Criterion.DURATION, None)
    checks: list[bool | None] = []
    if incident is not None and now is not None:
        hours, final = incident.duration_hours(now)
    elif a.duration_hours is not None:
        hours, final = a.duration_hours, True
    else:
        hours, final = 0.0, False
    if hours > th.duration_hours:
        checks.append(True)
        r.triggers.append(Trigger("duration", f"{hours:.1f} h", f"> {th.duration_hours:g} h"))
    elif final:
        checks.append(False)
    else:
        checks.append(None)
        r.open_questions.append("duration_hours")
    if a.downtime_hours is None:
        checks.append(None)
        r.open_questions.append("downtime_hours")
    elif a.downtime_hours > th.downtime_hours:
        checks.append(True)
        r.triggers.append(Trigger("downtime", f"{a.downtime_hours:g} h",
                                  f"> {th.downtime_hours:g} h"))
    else:
        checks.append(False)
    r.met = _any(checks)
    if r.met:
        r.open_questions = []
    return r


def _geography(a: Answers, th: Thresholds) -> CriterionResult:
    r = CriterionResult(Criterion.GEOGRAPHY, None)
    if a.member_states is None:
        r.open_questions.append("member_states")
        return r
    states = [c for c in a.member_states if c in EEA_COUNTRIES]
    r.met = len(states) >= th.member_states
    if r.met:
        r.triggers.append(Trigger("member_states", ", ".join(states),
                                  f"≥ {th.member_states}"))
    return r


def _economic(a: Answers, th: Thresholds) -> CriterionResult:
    r = CriterionResult(Criterion.ECONOMIC, None)
    if a.economic_eur is None:
        r.open_questions.append("economic_eur")
        return r
    r.met = a.economic_eur > th.economic_eur
    if r.met:
        r.triggers.append(Trigger("economic", f"EUR {a.economic_eur:,.0f}",
                                  f"> EUR {th.economic_eur:,.0f}"))
    return r


def classify_answers(a: Answers, th: Thresholds = DEFAULT_THRESHOLDS,
                     incident: Incident | None = None,
                     now: datetime | None = None) -> Classification:
    results: dict[Criterion, CriterionResult] = {}
    crit = CriterionResult(Criterion.CRITICAL_SERVICES, a.critical_services)
    if a.critical_services is None:
        crit.open_questions.append("critical_services")
    elif a.critical_services:
        crit.triggers.append(Trigger("critical_services", "yes", "required"))
    results[Criterion.CRITICAL_SERVICES] = crit
    results[Criterion.CLIENTS] = _clients(a, th)
    results[Criterion.REPUTATION] = _bools(Criterion.REPUTATION, [
        ("media", a.media), ("complaints", a.complaints),
        ("regulatory_breach", a.regulatory_breach), ("client_loss", a.client_loss)])
    results[Criterion.DURATION] = _duration(incident, a, th, now)
    results[Criterion.GEOGRAPHY] = _geography(a, th)
    results[Criterion.DATA] = _bools(Criterion.DATA, [("data_impact", a.data_impact)])
    results[Criterion.ECONOMIC] = _economic(a, th)
    met = sum(1 for c in COUNTED if results[c].met is True)
    possible = sum(1 for c in COUNTED if results[c].met is not False)
    low = crit.met is True and (a.malicious_access is True or met >= 2)
    high = crit.met is not False and (a.malicious_access is not False or possible >= 2)
    outcome = Outcome.MAJOR if low else (Outcome.NOT_MAJOR if not high
                                         else Outcome.UNDETERMINED)
    if outcome is not Outcome.UNDETERMINED:  # unknowns can no longer change the outcome
        for r in results.values():
            r.open_questions = []
    return Classification(outcome, results, a.malicious_access, met, possible)


def classify(incident: Incident, now: datetime, th: Thresholds = DEFAULT_THRESHOLDS
             ) -> Classification:
    return classify_answers(incident.answers, th, incident, now)


# =========================================================================== recurring


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year = moment.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31,
            30, 31, 31, 30, 31, 30, 31][month - 1]
    return moment.replace(year=year, month=month, day=min(moment.day, days))


def _sum(values: list[int | None]) -> int | None:
    return None if any(v is None for v in values) else sum(v for v in values if v is not None)


def _dsum(values: list[Decimal | None]) -> Decimal | None:
    return None if any(v is None for v in values) else sum(
        (v for v in values if v is not None), Decimal(0))


def _fsum(values: list[float | None]) -> float | None:
    return None if any(v is None for v in values) else sum(v for v in values if v is not None)


def _imax(values: list[int | None]) -> int | None:
    known = [v for v in values if v is not None]
    return max(known) if known else None


def _dmax(values: list[Decimal | None]) -> Decimal | None:
    known = [v for v in values if v is not None]
    return max(known) if known else None


def aggregate(incidents: list[Incident], now: datetime) -> Answers:
    """Combined answers of several incidents (A-INC-05): counts, durations and costs are
    added, totals take the largest denominator, yes/no answers are true if any is true, and
    Member States are united."""
    ans = [i.answers for i in incidents]
    durations: list[float | None] = []
    for i in incidents:
        hours, final = i.duration_hours(now)
        durations.append(hours if final else None)
    states: list[str] | None = None
    if all(a.member_states is not None for a in ans):
        states = sorted({c for a in ans for c in a.member_states or []})
    return Answers(
        critical_services=_any([a.critical_services for a in ans]),
        malicious_access=_any([a.malicious_access for a in ans]),
        clients_affected=_sum([a.clients_affected for a in ans]),
        clients_total=_imax([a.clients_total for a in ans]),
        counterparts_affected=_sum([a.counterparts_affected for a in ans]),
        counterparts_total=_imax([a.counterparts_total for a in ans]),
        relevant_clients=_any([a.relevant_clients for a in ans]),
        transactions_affected=_sum([a.transactions_affected for a in ans]),
        transactions_daily=_imax([a.transactions_daily for a in ans]),
        transaction_value_affected=_dsum([a.transaction_value_affected for a in ans]),
        transaction_value_daily=_dmax([a.transaction_value_daily for a in ans]),
        media=_any([a.media for a in ans]), complaints=_any([a.complaints for a in ans]),
        regulatory_breach=_any([a.regulatory_breach for a in ans]),
        client_loss=_any([a.client_loss for a in ans]),
        duration_hours=_fsum(durations),
        downtime_hours=_fsum([a.downtime_hours for a in ans]),
        member_states=states, data_impact=_any([a.data_impact for a in ans]),
        economic_eur=_dsum([a.economic_eur for a in ans]))


@dataclass
class RecurringGroup:
    key: str
    incidents: list[Incident]
    window_start: datetime
    window_end: datetime
    answers: Answers
    classification: Classification

    @property
    def major(self) -> bool:
        return self.classification.major


def recurring_groups(log: IncidentLog, now: datetime,
                     th: Thresholds = DEFAULT_THRESHOLDS) -> list[RecurringGroup]:
    """Groups of individually non-major incidents with the same recurrence key that occurred
    at least twice within ``th.recurrence_months`` – with their combined classification."""
    by_key: dict[str, list[Incident]] = {}
    for inc in log.incidents.values():
        if not inc.recurrence_key.strip() or classify(inc, now, th).major:
            continue
        by_key.setdefault(inc.recurrence_key.strip().casefold(), []).append(inc)
    groups: list[RecurringGroup] = []
    for items in by_key.values():
        items.sort(key=lambda i: i.start)
        best: list[Incident] = []
        for idx, first in enumerate(items):
            end = add_months(first.start, th.recurrence_months)
            window = [i for i in items[idx:] if i.start <= end]
            if len(window) > len(best):
                best = window
        if len(best) < 2:
            continue
        combined = aggregate(best, now)
        groups.append(RecurringGroup(
            best[0].recurrence_key.strip(), best, best[0].start,
            add_months(best[0].start, th.recurrence_months), combined,
            classify_answers(combined, th)))
    groups.sort(key=lambda g: (not g.major, g.window_start))
    return groups
