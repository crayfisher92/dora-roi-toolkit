"""Notice-deadline schedule: by when must notice be given to exit or renegotiate? (B-21)

For each arrangement with a fixed end date after the reference date, the notice deadline is
``end date − notice period of the financial entity`` (B_02.02 c0080 and c0100). Missing this
date usually means the arrangement renews or continues, so the planned exit (DORA Art. 28(8))
or renegotiation slips by a full term.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from dora_roi.model import RegisterOfInformation
from dora_roi.model.types import INDEFINITE_END_DATE


class NoticeStatus(StrEnum):
    PASSED = "passed"  # deadline missed, arrangement still running
    DUE_90 = "due_90"
    DUE_365 = "due_365"
    LATER = "later"


@dataclass
class NoticeItem:
    contract_ref: str
    provider: str
    provider_code: str
    entities: list[str]
    end_date: date
    notice_days: int | None
    deadline: date
    days_to_deadline: int
    critical: bool
    functions: list[str] = field(default_factory=list)

    @property
    def status(self) -> NoticeStatus:
        if self.days_to_deadline < 0:
            return NoticeStatus.PASSED
        if self.days_to_deadline <= 90:
            return NoticeStatus.DUE_90
        if self.days_to_deadline <= 365:
            return NoticeStatus.DUE_365
        return NoticeStatus.LATER


def notice_schedule(register: RegisterOfInformation, reference_date: date | None = None
                    ) -> list[NoticeItem]:
    """Arrangements with a fixed future end date, sorted by notice deadline."""
    ref = reference_date or register.reference_date or date.today()
    providers = register.providers_by_code()
    entities = register.entities_by_lei()
    is_critical = register.critical_checker()
    items: dict[str, NoticeItem] = {}
    for s in register.b_02_02:
        if not (s.contract_ref and s.end_date) or s.end_date == INDEFINITE_END_DATE:
            continue
        if s.end_date <= ref:
            continue
        p = providers.get(s.provider_code or "")
        notice = s.notice_period_entity
        deadline = s.end_date - timedelta(days=notice or 0)
        item = items.get(s.contract_ref)
        if item is None or deadline < item.deadline:
            prev = item
            item = NoticeItem(s.contract_ref, (p.legal_name if p and p.legal_name
                                               else s.provider_code or "—"),
                              s.provider_code or "", [], s.end_date, notice, deadline,
                              (deadline - ref).days, False)
            if prev is not None:
                item.entities, item.functions, item.critical = (prev.entities, prev.functions,
                                                                prev.critical)
            items[s.contract_ref] = item
        ent = entities.get(s.entity_lei or "")
        name = ent.name if ent and ent.name else (s.entity_lei or "")
        if name and name not in item.entities:
            item.entities.append(name)
        if s.function_id and s.function_id not in item.functions:
            item.functions.append(s.function_id)
        item.critical |= is_critical(s)
    return sorted(items.values(), key=lambda i: (i.deadline, i.contract_ref))
