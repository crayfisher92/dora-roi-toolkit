"""Incident log: incidents with classification answers, timestamps, register links and history.

Timestamps are timezone-aware and stored in UTC; the log has a display time zone (default
``Europe/Berlin``) used by the forms and reports. Classification is **derived** from the
answers each time (:mod:`dora_roi.incidents.classify`) so it can never disagree with them;
the history records what was decided and when.

JSON format: ``dora-roi-toolkit/incident-log/v1``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, tzinfo
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dora_roi import __version__

SCHEMA = "dora-roi-toolkit/incident-log/v1"
DEFAULT_TIMEZONE = "Europe/Berlin"
TIMEZONES = ("Europe/Berlin", "Europe/Zurich", "Europe/Luxembourg", "Europe/Vienna",
             "Europe/Paris", "Europe/Rome", "Europe/Amsterdam", "Europe/Dublin",
             "Europe/London", "UTC")


def zone(name: str) -> tzinfo:
    """The named time zone, falling back to UTC when tz data is unavailable."""
    if name == "UTC":
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RootCause(StrEnum):
    """Root-cause category (paraphrasing the reporting ITS; see A-INC-07)."""

    MALICIOUS = "malicious_action"
    PROCESS = "process_failure"
    SYSTEM = "system_failure"
    HUMAN = "human_error"
    EXTERNAL = "external_event"
    THIRD_PARTY = "third_party_failure"
    UNKNOWN = "unknown"


class ReportKind(StrEnum):
    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    FINAL = "final"


class Answers(BaseModel):
    """Answers to the classification questionnaire. ``None`` = not known (yet)."""

    model_config = ConfigDict(extra="forbid")

    critical_services: bool | None = None
    malicious_access: bool | None = None
    clients_affected: int | None = Field(default=None, ge=0)
    clients_total: int | None = Field(default=None, ge=0)
    counterparts_affected: int | None = Field(default=None, ge=0)
    counterparts_total: int | None = Field(default=None, ge=0)
    relevant_clients: bool | None = None
    transactions_affected: int | None = Field(default=None, ge=0)
    transactions_daily: int | None = Field(default=None, ge=0)
    transaction_value_affected: Decimal | None = Field(default=None, ge=0)
    transaction_value_daily: Decimal | None = Field(default=None, ge=0)
    media: bool | None = None
    complaints: bool | None = None
    regulatory_breach: bool | None = None
    client_loss: bool | None = None
    #: Explicit duration in hours; when empty it is computed from the timestamps.
    duration_hours: float | None = Field(default=None, ge=0)
    downtime_hours: float | None = Field(default=None, ge=0)
    #: ISO codes of EU/EEA Member States with an impact; ``None`` = not assessed.
    member_states: list[str] | None = None
    data_impact: bool | None = None
    economic_eur: Decimal | None = Field(default=None, ge=0)

    @field_validator("member_states")
    @classmethod
    def _codes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return sorted({v.strip().upper() for v in value if v and v.strip()})


class IncidentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    by: str = ""
    action: str
    note: str = ""


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: IncidentStatus = IncidentStatus.OPEN
    owner: str = Field(default="", max_length=200)
    occurred_at: datetime | None = None
    #: Moment the financial entity became aware of the incident (starts the 24 h clock).
    detected_at: datetime
    classified_at: datetime | None = None
    resolved_at: datetime | None = None
    entity_leis: list[str] = Field(default_factory=list)
    provider_codes: list[str] = Field(default_factory=list)
    contract_refs: list[str] = Field(default_factory=list)
    root_cause: RootCause | None = None
    #: Grouping key for "same apparent root cause" (recurring incidents).
    recurrence_key: str = Field(default="", max_length=120)
    answers: Answers = Field(default_factory=Answers)
    initial_submitted_at: datetime | None = None
    intermediate_submitted_at: datetime | None = None
    final_submitted_at: datetime | None = None
    authority_reference: str = Field(default="", max_length=120)
    history: list[IncidentEvent] = Field(default_factory=list)

    @field_validator("occurred_at", "detected_at", "classified_at", "resolved_at",
                     "initial_submitted_at", "intermediate_submitted_at", "final_submitted_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _chronology(self) -> Incident:
        problem = timeline_problem(self)
        if problem is not None:
            raise ValueError(f"{problem}: timestamps out of order")
        return self

    @property
    def start(self) -> datetime:
        """Start of the incident for the duration (occurrence, else awareness)."""
        return self.occurred_at or self.detected_at

    def duration_hours(self, now: datetime) -> tuple[float, bool]:
        """``(hours, final)``; not final while the incident is unresolved."""
        if self.answers.duration_hours is not None:
            return self.answers.duration_hours, True
        end = self.resolved_at or now
        hours = max((end - self.start) / timedelta(hours=1), 0.0)
        return hours, self.resolved_at is not None

    def submitted(self, kind: ReportKind) -> datetime | None:
        return {ReportKind.INITIAL: self.initial_submitted_at,
                ReportKind.INTERMEDIATE: self.intermediate_submitted_at,
                ReportKind.FINAL: self.final_submitted_at}[kind]


def timeline_problem(incident: Incident) -> str | None:
    """The first timestamp that contradicts the chronology of an incident, if any.

    occurred ≤ aware ≤ classified; start ≤ resolved; aware ≤ initial ≤ intermediate ≤ final
    report. Equal times are allowed.
    """
    aware = incident.detected_at
    checks: list[tuple[str, datetime | None, datetime | None]] = [
        ("occurred_at", incident.occurred_at, aware),
        ("classified_at", aware, incident.classified_at),
        ("resolved_at", incident.occurred_at or aware, incident.resolved_at),
        ("initial_submitted_at", aware, incident.initial_submitted_at),
        ("intermediate_submitted_at", incident.initial_submitted_at,
         incident.intermediate_submitted_at),
        ("final_submitted_at", incident.intermediate_submitted_at, incident.final_submitted_at),
    ]
    for name, earlier, later in checks:
        if earlier is not None and later is not None and later < earlier:
            return name
    return None


class IncidentLog(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=SCHEMA, alias="schema")
    toolkit_version: str = __version__
    timezone: str = DEFAULT_TIMEZONE
    incidents: dict[str, Incident] = Field(default_factory=dict)

    @property
    def tz(self) -> tzinfo:
        return zone(self.timezone)

    def __len__(self) -> int:
        return len(self.incidents)

    def get(self, incident_id: str) -> Incident | None:
        return self.incidents.get(incident_id)

    def ordered(self) -> list[Incident]:
        """Newest first."""
        return sorted(self.incidents.values(), key=lambda i: i.detected_at, reverse=True)

    def next_id(self, when: datetime) -> str:
        year = when.astimezone(self.tz).year
        prefix = f"INC-{year}-"
        used = [int(i[len(prefix):]) for i in self.incidents
                if i.startswith(prefix) and i[len(prefix):].isdigit()]
        return f"{prefix}{max(used, default=0) + 1:03d}"

    def save(self, incident: Incident, action: str, by: str = "", note: str = "",
             at: datetime | None = None) -> Incident:
        old = self.incidents.get(incident.id)
        history = list(old.history) if old else list(incident.history)
        history.append(IncidentEvent(at=at or datetime.now(UTC), by=by, action=action,
                                     note=note))
        stored = incident.model_copy(update={"history": history})
        self.incidents[incident.id] = stored
        return stored

    def remove(self, incident_id: str) -> None:
        self.incidents.pop(incident_id, None)

    def merge(self, other: IncidentLog, source: str = "", by: str = "",
              at: datetime | None = None) -> tuple[int, int]:
        """Take over the incidents of ``other``; returns ``(new, updated)``. Existing history is
        kept and combined with the imported one, plus an import entry (as for assessments)."""
        new = updated = 0
        when = at or datetime.now(UTC)
        for iid, inc in other.incidents.items():
            old = self.incidents.get(iid)
            seen: set[tuple[datetime, str, str, str]] = set()
            history: list[IncidentEvent] = []
            for e in sorted([*(old.history if old else []), *inc.history], key=lambda e: e.at):
                key = (e.at, e.by, e.action, e.note)
                if key not in seen:
                    seen.add(key)
                    history.append(e)
            history.append(IncidentEvent(at=when, by=by, action="imported",
                                         note=source[:200]))
            self.incidents[iid] = inc.model_copy(update={"history": history})
            if old is None:
                new += 1
            else:
                updated += 1
        return new, updated

    def to_json(self) -> str:
        return self.model_dump_json(by_alias=True, indent=2, exclude_none=True)

    @classmethod
    def from_json(cls, text: str | bytes) -> IncidentLog:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError(f"not an incident log (expected schema {SCHEMA!r})")
        return cls.model_validate(data)
