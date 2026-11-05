"""Major ICT-related incident classification (DORA Art. 18/19), reporting deadlines and log.

Typical use::

    from dora_roi.incidents import Answers, classify_answers
    result = classify_answers(Answers(critical_services=True, downtime_hours=3,
                                      member_states=["DE", "LU"]))
    result.outcome            # Outcome.MAJOR
"""

from dora_roi.incidents.classify import (
    Classification,
    CriterionResult,
    Outcome,
    RecurringGroup,
    classify,
    classify_answers,
    recurring_groups,
)
from dora_roi.incidents.criteria import DEFAULT_THRESHOLDS, Criterion, Thresholds, criteria
from dora_roi.incidents.deadlines import Deadline, DeadlineState, timeline
from dora_roi.incidents.model import (
    Answers,
    Incident,
    IncidentEvent,
    IncidentLog,
    IncidentStatus,
    ReportKind,
    RootCause,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "Answers",
    "Classification",
    "Criterion",
    "CriterionResult",
    "Deadline",
    "DeadlineState",
    "Incident",
    "IncidentEvent",
    "IncidentLog",
    "IncidentStatus",
    "Outcome",
    "RecurringGroup",
    "ReportKind",
    "RootCause",
    "Thresholds",
    "classify",
    "classify_answers",
    "criteria",
    "recurring_groups",
    "timeline",
]
