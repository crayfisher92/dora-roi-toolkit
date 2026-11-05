"""Contract compliance with DORA Art. 30, per contract, per provider and as a remediation plan.

The register is the source of truth for *what* a contract is: its providers (B_02.02 c0030,
B_03.02), the entities using it, the functions it supports and therefore whether Art. 30(3)
applies (a B_02.02 row supporting a critical or important function, B_06.01 c0050). The
assessment book only says *what the contract contains*.

Subsequent arrangements (B_02.01 c0020 = subsequent/associated, c0030 = overarching
reference) inherit the items of their overarching arrangement unless they are assessed
themselves – call-offs under a master agreement usually rely on its terms (D-049).

Remediation priority (D-050):

========================  ===============  ===============
status                    supports a CIF   does not
========================  ===============  ===============
missing                   high             medium
partial                   medium           low
========================  ===============  ===============

Within a priority, gaps in *key* provisions (★ in the checklist) are listed first.
Unassessed applicable provisions are listed separately as "to assess".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from dora_roi.contracts.model import (
    AssessmentBook,
    ContractAssessment,
    ProvisionAssessment,
    ProvisionStatus,
)
from dora_roi.contracts.provisions import PROVISIONS, Provision, applicable
from dora_roi.model import ContractType, RegisterOfInformation
from dora_roi.model.types import INDEFINITE_END_DATE


class ComplianceStatus(StrEnum):
    COMPLIANT = "compliant"
    GAPS = "gaps"
    #: Every gap is covered by an approved, unexpired exception (D-071) – not compliant.
    EXCEPTION = "exception"
    INCOMPLETE = "incomplete"
    NOT_ASSESSED = "not_assessed"

    @property
    def rank(self) -> int:
        """Lower is worse (for sorting)."""
        return {"gaps": 0, "incomplete": 1, "not_assessed": 2, "exception": 3,
                "compliant": 4}[self.value]


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"high": 0, "medium": 1, "low": 2}[self.value]


#: Days from the plan date to the suggested remediation target, per priority (D-050).
TARGET_DAYS = {Priority.HIGH: 90, Priority.MEDIUM: 180, Priority.LOW: 365}


@dataclass(frozen=True)
class FunctionRef:
    function_id: str
    entity_lei: str
    name: str
    critical: bool


@dataclass
class ContractContext:
    """What the register says about one contractual arrangement."""

    contract_ref: str
    in_register: bool = True
    contract_type: ContractType | None = None
    overarching_ref: str | None = None
    annual_cost: Decimal | None = None
    currency: str | None = None
    providers: dict[str, str] = field(default_factory=dict)  # code -> name
    entities: dict[str, str] = field(default_factory=dict)  # lei -> name
    functions: list[FunctionRef] = field(default_factory=list)
    service_types: list[str] = field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    row: int | None = None

    @property
    def critical(self) -> bool:
        return any(f.critical for f in self.functions)

    @property
    def critical_functions(self) -> list[FunctionRef]:
        return [f for f in self.functions if f.critical]

    @property
    def provider_names(self) -> str:
        return ", ".join(sorted(self.providers.values())) or "—"

    @property
    def open_ended(self) -> bool:
        return self.end_date is None or self.end_date == INDEFINITE_END_DATE


def contract_contexts(register: RegisterOfInformation) -> dict[str, ContractContext]:
    """One :class:`ContractContext` per B_02.01 record (plus arrangements only in B_02.02)."""
    providers = register.providers_by_code()
    entities = register.entities_by_lei()
    fl = register.function_lookup()
    by_id = register.functions_by_id()
    out: dict[str, ContractContext] = {}
    for c in register.b_02_01:
        if not c.contract_ref or c.contract_ref in out:
            continue
        out[c.contract_ref] = ContractContext(
            c.contract_ref, contract_type=c.contract_type, overarching_ref=c.overarching_ref,
            annual_cost=c.annual_cost, currency=c.currency, row=c.row)
    for s in register.b_02_02:
        if not s.contract_ref:
            continue
        ctx = out.get(s.contract_ref)
        if ctx is None:
            ctx = out[s.contract_ref] = ContractContext(s.contract_ref, in_register=False)
        if s.provider_code:
            p = providers.get(s.provider_code)
            ctx.providers[s.provider_code] = (p.legal_name if p and p.legal_name
                                              else s.provider_code)
        if s.entity_lei:
            e = entities.get(s.entity_lei)
            ctx.entities[s.entity_lei] = e.name if e and e.name else s.entity_lei
        if s.service_type and s.service_type.value not in ctx.service_types:
            ctx.service_types.append(s.service_type.value)
        if s.function_id:
            fn = fl.get((s.function_id, s.entity_lei or ""))
            candidates = [fn] if fn else by_id.get(s.function_id, [])
            critical = any(f.is_critical for f in candidates)
            name = next((f.function_name for f in candidates if f.function_name), s.function_id)
            ref = FunctionRef(s.function_id, s.entity_lei or "", name or s.function_id, critical)
            if ref not in ctx.functions:
                ctx.functions.append(ref)
        if s.start_date and (ctx.start_date is None or s.start_date < ctx.start_date):
            ctx.start_date = s.start_date
        if s.end_date and (ctx.end_date is None or s.end_date > ctx.end_date):
            ctx.end_date = s.end_date
    for sig in register.b_03_02:  # signing providers without a B_02.02 row
        signed = out.get(sig.contract_ref or "")
        if signed is not None and sig.provider_code and sig.provider_code not in signed.providers:
            p = providers.get(sig.provider_code)
            signed.providers[sig.provider_code] = (p.legal_name if p and p.legal_name
                                                   else sig.provider_code)
    return out


@dataclass(frozen=True)
class EffectiveItem:
    provision: Provision
    status: ProvisionStatus
    clause_ref: str = ""
    evidence: str = ""
    #: Arrangement reference the item was inherited from (overarching arrangement), if any.
    inherited_from: str | None = None
    suggested_status: ProvisionStatus | None = None
    exception_reason: str = ""
    exception_approver: str = ""
    exception_until: date | None = None
    #: True when the gap is covered by an exception that has not expired on the as-of date.
    excepted: bool = False

    @property
    def is_gap(self) -> bool:
        return self.status in (ProvisionStatus.MISSING, ProvisionStatus.PARTIAL)

    @property
    def is_open_gap(self) -> bool:
        return self.is_gap and not self.excepted

    @property
    def exception_expired(self) -> bool:
        return self.is_gap and bool(self.exception_reason) and not self.excepted


@dataclass
class ContractCompliance:
    context: ContractContext
    assessment: ContractAssessment | None
    items: list[EffectiveItem]
    status: ComplianceStatus
    inherited_from: str | None = None

    @property
    def ref(self) -> str:
        return self.context.contract_ref

    def count(self, status: ProvisionStatus) -> int:
        return sum(1 for i in self.items if i.status is status)

    @property
    def missing(self) -> int:
        return self.count(ProvisionStatus.MISSING)

    @property
    def partial(self) -> int:
        return self.count(ProvisionStatus.PARTIAL)

    @property
    def present(self) -> int:
        return self.count(ProvisionStatus.PRESENT)

    @property
    def unassessed(self) -> int:
        return self.count(ProvisionStatus.NOT_ASSESSED)

    @property
    def gaps(self) -> list[EffectiveItem]:
        """Open gaps (missing/partial without a valid exception)."""
        return [i for i in self.items if i.is_open_gap]

    @property
    def exceptions(self) -> list[EffectiveItem]:
        return [i for i in self.items if i.excepted]

    @property
    def assessed(self) -> bool:
        return self.status is not ComplianceStatus.NOT_ASSESSED

    @property
    def coverage(self) -> float:
        """Share of applicable provisions assessed as present."""
        return self.present / len(self.items) if self.items else 0.0


def _status_of(items: list[EffectiveItem]) -> ComplianceStatus:
    statuses = {i.status for i in items}
    if statuses <= {ProvisionStatus.NOT_ASSESSED}:
        return ComplianceStatus.NOT_ASSESSED
    if any(i.is_open_gap for i in items):
        return ComplianceStatus.GAPS
    if ProvisionStatus.NOT_ASSESSED in statuses:
        return ComplianceStatus.INCOMPLETE
    if any(i.excepted for i in items):
        return ComplianceStatus.EXCEPTION
    return ComplianceStatus.COMPLIANT


def _effective(p: Provision, a: ProvisionAssessment, on: date, inherited: str | None = None
               ) -> EffectiveItem:
    return EffectiveItem(p, a.status, a.clause_ref, a.evidence, inherited,
                         a.suggested_status if inherited is None else None,
                         a.exception_reason, a.exception_approver, a.exception_until,
                         a.exception_valid(on))


def evaluate_contract(ctx: ContractContext, book: AssessmentBook,
                      as_of: date | None = None) -> ContractCompliance:
    on = as_of or date.today()
    own = book.get(ctx.contract_ref)
    parent_ref = ctx.overarching_ref if ctx.contract_type is ContractType.SUBSEQUENT else None
    parent = book.get(parent_ref) if parent_ref and (own is None or own.inherit) else None
    items: list[EffectiveItem] = []
    inherited_any = False
    for p in applicable(ctx.critical):
        mine = own.items.get(p.id) if own else None
        if mine is not None and mine.status is not ProvisionStatus.NOT_ASSESSED:
            items.append(_effective(p, mine, on))
            continue
        theirs = parent.items.get(p.id) if parent else None
        if theirs is not None and theirs.status is not ProvisionStatus.NOT_ASSESSED:
            inherited_any = True
            items.append(_effective(p, theirs, on, parent_ref))
            continue
        items.append(EffectiveItem(p, ProvisionStatus.NOT_ASSESSED,
                                   mine.clause_ref if mine else "",
                                   mine.evidence if mine else "",
                                   suggested_status=mine.suggested_status if mine else None))
    return ContractCompliance(ctx, own, items, _status_of(items),
                              inherited_from=parent_ref if inherited_any else None)


@dataclass
class ProviderCompliance:
    code: str
    name: str
    contracts: list[ContractCompliance] = field(default_factory=list)
    critical_functions: set[tuple[str, str]] = field(default_factory=set)

    @property
    def missing(self) -> int:
        return sum(c.missing for c in self.contracts)

    @property
    def partial(self) -> int:
        return sum(c.partial for c in self.contracts)

    @property
    def assessed(self) -> int:
        return sum(1 for c in self.contracts if c.assessed)

    @property
    def with_gaps(self) -> int:
        return sum(1 for c in self.contracts if c.status is ComplianceStatus.GAPS)

    @property
    def status(self) -> ComplianceStatus:
        return min((c.status for c in self.contracts), key=lambda s: s.rank,
                   default=ComplianceStatus.NOT_ASSESSED)

    @property
    def critical(self) -> bool:
        return bool(self.critical_functions)


@dataclass
class Portfolio:
    contracts: list[ContractCompliance]
    providers: list[ProviderCompliance]
    #: Assessments whose arrangement reference is not in B_02.01/B_02.02.
    orphans: list[ContractAssessment]

    def by_ref(self) -> dict[str, ContractCompliance]:
        return {c.ref: c for c in self.contracts}

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in ComplianceStatus}
        for c in self.contracts:
            out[c.status.value] += 1
        return out

    @property
    def critical_contracts(self) -> list[ContractCompliance]:
        return [c for c in self.contracts if c.context.critical]

    @property
    def total_missing(self) -> int:
        return sum(c.missing for c in self.contracts)

    @property
    def total_partial(self) -> int:
        return sum(c.partial for c in self.contracts)

    def critical_assessed_share(self) -> float:
        crit = self.critical_contracts
        return sum(1 for c in crit if c.assessed) / len(crit) if crit else 1.0


def evaluate(register: RegisterOfInformation, book: AssessmentBook,
             as_of: date | None = None) -> Portfolio:
    """Evaluate every arrangement of the register against its assessment; exceptions are
    valid if they have not expired on ``as_of`` (default: today)."""
    contexts = contract_contexts(register)
    contracts = [evaluate_contract(ctx, book, as_of) for ctx in contexts.values()]
    providers: dict[str, ProviderCompliance] = {}
    for c in contracts:
        for code, name in c.context.providers.items():
            pc = providers.setdefault(code, ProviderCompliance(code, name))
            pc.contracts.append(c)
            pc.critical_functions |= {(f.function_id, f.entity_lei)
                                      for f in c.context.critical_functions}
    ordered = sorted(providers.values(), key=lambda p: (
        -len(p.critical_functions), p.status.rank, -p.missing, -p.partial, p.name.casefold()))
    for p in ordered:
        p.contracts.sort(key=lambda c: (not c.context.critical, c.status.rank, -c.missing,
                                        c.ref))
    orphans = [a for ref, a in book.assessments.items() if ref not in contexts]
    contracts.sort(key=lambda c: (not c.context.critical, c.status.rank, -c.missing, c.ref))
    return Portfolio(contracts, ordered, orphans)


# =========================================================================== remediation


def priority(item: EffectiveItem, critical: bool) -> Priority:
    if item.status is ProvisionStatus.MISSING:
        return Priority.HIGH if critical else Priority.MEDIUM
    return Priority.MEDIUM if critical else Priority.LOW


@dataclass(frozen=True)
class RemediationItem:
    priority: Priority
    contract_ref: str
    providers: str
    entities: str
    critical_functions: str
    critical: bool
    provision: Provision
    status: ProvisionStatus
    clause_ref: str
    evidence: str
    inherited_from: str | None
    target_date: date
    contract_end: date | None
    #: Subsequent arrangements (call-offs) that rely on this clause of the arrangement.
    applies_to: tuple[str, ...] = ()

    def action(self, lang: str = "en") -> str:
        return self.provision.remediation(lang)


@dataclass(frozen=True)
class ExceptionItem:
    contract_ref: str
    providers: str
    critical: bool
    provision: Provision
    status: ProvisionStatus
    reason: str
    approver: str
    until: date | None
    inherited_from: str | None


@dataclass
class RemediationPlan:
    plan_date: date
    items: list[RemediationItem]
    to_assess: list[ContractCompliance]
    portfolio: Portfolio
    #: Approved exceptions, earliest expiry first (inherited ones only at the master).
    exceptions: list[ExceptionItem] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = {p.value: 0 for p in Priority}
        for i in self.items:
            out[i.priority.value] += 1
        return out


def _item(c: ContractCompliance, it: EffectiveItem, today: date, critical: bool,
          applies_to: tuple[str, ...] = ()) -> RemediationItem:
    ctx = c.context
    prio = priority(it, critical)
    return RemediationItem(
        prio, ctx.contract_ref, ctx.provider_names,
        ", ".join(sorted(ctx.entities.values())) or "—",
        "; ".join(f"{f.function_id} {f.name}" for f in ctx.critical_functions),
        critical, it.provision, it.status, it.clause_ref, it.evidence, it.inherited_from,
        today + timedelta(days=TARGET_DAYS[prio]), None if ctx.open_ended else ctx.end_date,
        applies_to)


def remediation_plan(portfolio: Portfolio, plan_date: date | None = None) -> RemediationPlan:
    """Gaps as prioritised actions.

    A gap inherited by call-offs is fixed once, in the overarching arrangement: it is listed
    there (with the call-offs in ``applies_to``, and escalated if a call-off supports a
    critical function). Only when the overarching arrangement does not list that provision
    itself (e.g. an Art. 30(3) item of a non-critical master) is it listed under the call-off.
    """
    today = plan_date or date.today()
    items: list[RemediationItem] = []
    listed: dict[tuple[str, str], int] = {}
    by_ref = portfolio.by_ref()
    for c in portfolio.contracts:
        for it in c.gaps:
            if it.inherited_from is None:
                listed[(c.ref, it.provision.id)] = len(items)
                items.append(_item(c, it, today, c.context.critical))
    for c in portfolio.contracts:
        for it in c.gaps:
            if it.inherited_from is None:
                continue
            key = (it.inherited_from, it.provision.id)
            if key in listed:
                idx = listed[key]
                old = items[idx]
                parent = by_ref.get(it.inherited_from)
                critical = old.critical or c.context.critical
                if parent is not None and critical != old.critical:
                    parent_item = next(i for i in parent.items if i.provision.id == key[1])
                    items[idx] = _item(parent, parent_item, today, True, old.applies_to)
                    old = items[idx]
                items[idx] = replace(old, applies_to=(*old.applies_to, c.ref))
            else:
                listed[(c.ref, it.provision.id)] = len(items)
                items.append(_item(c, it, today, c.context.critical))
    order = {p.id: i for i, p in enumerate(PROVISIONS)}
    items.sort(key=lambda i: (i.priority.rank, not i.critical, not i.provision.key,
                              i.providers.casefold(), i.contract_ref, order[i.provision.id]))
    to_assess = [c for c in portfolio.contracts
                 if c.status in (ComplianceStatus.NOT_ASSESSED, ComplianceStatus.INCOMPLETE)]
    to_assess.sort(key=lambda c: (not c.context.critical, c.status.rank, c.ref))
    exceptions = [ExceptionItem(c.ref, c.context.provider_names, c.context.critical,
                                it.provision, it.status, it.exception_reason,
                                it.exception_approver, it.exception_until, it.inherited_from)
                  for c in portfolio.contracts for it in c.exceptions if not it.inherited_from]
    exceptions.sort(key=lambda e: (e.until or date.max, e.contract_ref))
    return RemediationPlan(today, items, to_assess, portfolio, exceptions)


def gaps_by_provision(portfolio: Portfolio) -> list[tuple[Provision, int, int]]:
    """``(provision, missing, partial)`` across own (non-inherited) assessments."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for c in portfolio.contracts:
        for it in c.gaps:
            if it.inherited_from:
                continue
            counts[it.provision.id][0 if it.status is ProvisionStatus.MISSING else 1] += 1
    return [(p, counts[p.id][0], counts[p.id][1]) for p in PROVISIONS if p.id in counts]
