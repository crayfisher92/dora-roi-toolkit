"""Incident views linked to the register, and the exportable incident summary (HTML/JSON/MD)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dora_roi import __version__
from dora_roi.i18n import translator
from dora_roi.incidents.classify import (
    Classification,
    RecurrenceCandidate,
    RecurringGroup,
    classify,
    possible_recurrences,
    recurring_groups,
)
from dora_roi.incidents.criteria import COUNTED, DEFAULT_THRESHOLDS, Criterion, Thresholds, criteria
from dora_roi.incidents.deadlines import Deadline, DeadlineState, humanise, next_deadline, timeline
from dora_roi.incidents.model import Incident, IncidentLog, IncidentStatus, zone
from dora_roi.model import RegisterOfInformation
from dora_roi.model.refdata import EEA_COUNTRIES
from dora_roi.reporting.env import environment

SUMMARY_SCHEMA = "dora-roi-toolkit/incident-summary/v1"


@dataclass(frozen=True)
class Link:
    code: str
    name: str
    in_register: bool


@dataclass(frozen=True)
class FunctionLink:
    function_id: str
    name: str
    critical: bool


@dataclass
class IncidentView:
    incident: Incident
    classification: Classification
    deadlines: list[Deadline]
    providers: list[Link] = field(default_factory=list)
    contracts: list[Link] = field(default_factory=list)
    entities: list[Link] = field(default_factory=list)
    functions: list[FunctionLink] = field(default_factory=list)
    suggested_states: list[str] = field(default_factory=list)

    @property
    def next(self) -> Deadline | None:
        return next_deadline(self.deadlines)

    @property
    def supports_critical(self) -> bool:
        return any(f.critical for f in self.functions)

    def overdue(self, now: datetime) -> list[Deadline]:
        return [d for d in self.deadlines if d.state(now) is DeadlineState.OVERDUE]


def incident_view(incident: Incident, register: RegisterOfInformation | None, now: datetime,
                  th: Thresholds = DEFAULT_THRESHOLDS) -> IncidentView:
    c = classify(incident, now, th)
    view = IncidentView(incident, c, timeline(incident, c, now, th))
    reg = register or RegisterOfInformation()
    providers = reg.providers_by_code()
    view.providers = [Link(code, providers[code].legal_name or code if code in providers
                           else code, code in providers) for code in incident.provider_codes]
    refs = {r.contract_ref for r in reg.b_02_01}
    view.contracts = [Link(r, r, r in refs) for r in incident.contract_refs]
    entities = reg.entities_by_lei()
    view.entities = [Link(lei, entities[lei].name or lei if lei in entities else lei,
                          lei in entities) for lei in incident.entity_leis]
    fl = reg.function_lookup()
    seen: set[tuple[str, str]] = set()
    states: set[str] = set()
    for s in reg.b_02_02:
        if s.contract_ref not in incident.contract_refs:
            continue
        key = (s.function_id or "", s.entity_lei or "")
        fn = fl.get(key)
        if fn is not None and key not in seen:
            seen.add(key)
            view.functions.append(FunctionLink(fn.function_id or "", fn.function_name or "",
                                               fn.is_critical))
    for lei in incident.entity_leis:
        ent = entities.get(lei)
        if ent is not None and ent.country in EEA_COUNTRIES:
            states.add(ent.country)
        states |= {b.country for b in reg.b_01_03
                   if b.head_office_lei == lei and b.country in EEA_COUNTRIES}
    view.suggested_states = sorted(states)
    view.functions.sort(key=lambda f: (not f.critical, f.function_id))
    return view


@dataclass
class IncidentOverview:
    views: list[IncidentView]
    recurring: list[RecurringGroup]
    now: datetime
    candidates: list[RecurrenceCandidate] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.views),
            "open": sum(1 for v in self.views if v.incident.status is IncidentStatus.OPEN),
            "major": sum(1 for v in self.views if v.classification.major),
            "undetermined": sum(1 for v in self.views
                                if v.classification.outcome.value == "undetermined"),
            "overdue": sum(len(v.overdue(self.now)) for v in self.views),
            "recurring_major": sum(1 for g in self.recurring if g.major),
        }

    @property
    def open_major(self) -> list[IncidentView]:
        return [v for v in self.views if v.classification.major
                and (v.incident.status is IncidentStatus.OPEN
                     or any(d.submitted_at is None for d in v.deadlines))]

    def next_deadline(self) -> tuple[IncidentView, Deadline] | None:
        pending = [(v, d) for v in self.views for d in v.deadlines if d.submitted_at is None]
        return min(pending, key=lambda vd: vd[1].due) if pending else None


def overview(log: IncidentLog, register: RegisterOfInformation | None, now: datetime,
             th: Thresholds = DEFAULT_THRESHOLDS) -> IncidentOverview:
    views = [incident_view(i, register, now, th) for i in log.ordered()]
    return IncidentOverview(views, recurring_groups(log, now, th), now,
                            possible_recurrences(log, now, th))


# =========================================================================== exports


def _deadline_dict(d: Deadline, now: datetime) -> dict[str, Any]:
    return {"report": d.kind.value, "due": d.due.isoformat(), "basis": d.basis,
            "state": d.state(now).value,
            "submitted_at": d.submitted_at.isoformat() if d.submitted_at else None}


def _classification_dict(c: Classification) -> dict[str, Any]:
    return {
        "outcome": c.outcome.value, "basis": c.basis, "criteria_met": c.met_count,
        "malicious_access": c.malicious_access,
        "criteria": {k.value: {"met": r.met,
                               "triggers": [{"threshold": t.key, "value": t.value,
                                             "limit": t.limit} for t in r.triggers],
                               "open_questions": r.open_questions}
                     for k, r in c.results.items()},
        "open_questions": c.open_questions,
    }


def summary_dict(ov: IncidentOverview, timezone: str = "UTC") -> dict[str, Any]:
    """Machine-readable summary (classification and deadlines are derived, not stored)."""
    return {
        "schema": SUMMARY_SCHEMA, "toolkit_version": __version__,
        "generated_at": ov.now.isoformat(), "timezone": timezone, "counts": ov.counts(),
        "incidents": [{
            "id": v.incident.id, "title": v.incident.title, "status": v.incident.status.value,
            "detected_at": v.incident.detected_at.isoformat(),
            "classified_at": v.incident.classified_at.isoformat()
            if v.incident.classified_at else None,
            "resolved_at": v.incident.resolved_at.isoformat() if v.incident.resolved_at
            else None,
            "providers": [{"code": p.code, "name": p.name, "in_register": p.in_register}
                          for p in v.providers],
            "contracts": [c.code for c in v.contracts],
            "critical_functions": [f.function_id for f in v.functions if f.critical],
            "root_cause": v.incident.root_cause.value if v.incident.root_cause else None,
            "classification": _classification_dict(v.classification),
            "reporting": [_deadline_dict(d, ov.now) for d in v.deadlines],
        } for v in ov.views],
        "recurring": [{"key": g.key, "incidents": [i.id for i in g.incidents],
                       "window_start": g.window_start.isoformat(),
                       "window_end": g.window_end.isoformat(),
                       "classification": _classification_dict(g.classification)}
                      for g in ov.recurring],
    }


def summary_markdown(ov: IncidentOverview, lang: str = "en") -> str:
    t = translator(lang)
    c = ov.counts()
    lines = [f"# {t('inc.summary.title')}", "",
             t("inc.summary.counts", **c), "",
             f"| ID | {t('inc.title')} | {t('g.status')} | {t('inc.classification')} | "
             f"{t('inc.next_deadline')} |", "|---|---|---|---|---|"]
    for v in ov.views:
        nxt = next((d for d in v.deadlines if d.submitted_at is None), None)
        due = (f"{t('inc.report.' + nxt.kind.value)} {nxt.due:%Y-%m-%d %H:%M} UTC "
               f"({t('inc.dl.' + nxt.state(ov.now).value)})") if nxt else "—"
        title = v.incident.title.replace("|", "\\|")
        lines.append(f"| {v.incident.id} | {title} | {t('inc.st.' + v.incident.status.value)} "
                     f"| {t('inc.out.' + v.classification.outcome.value)} | {due} |")
    for g in ov.recurring:
        lines += ["", f"**{t('inc.recurring')}:** {g.key} – {', '.join(i.id for i in g.incidents)}"
                  f" → {t('inc.out.' + g.classification.outcome.value)}"]
    return "\n".join(lines) + "\n"


def render_summary_html(ov: IncidentOverview, *, lang: str = "en", client: str | None = None,
                        timezone: str = "UTC") -> str:
    tz = zone(timezone)
    ctx: dict[str, Any] = {
        "ov": ov, "t": translator(lang), "lang": lang, "client": client or "",
        "version": __version__, "criteria": {c.key: c for c in criteria()},
        "counted": COUNTED, "Criterion": Criterion,
        "local": lambda d: d.astimezone(tz).strftime("%Y-%m-%d %H:%M") if d else "—",
        "tzname": timezone, "humanise": lambda d: humanise(d, lang),
    }
    return environment().get_template("incidents.html.j2").render(**ctx)
