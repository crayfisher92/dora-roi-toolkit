"""Failure-impact analysis: what is affected if one ICT provider fails? (``BACKLOG`` B-03)

A provider can support a function **directly** (it is the contracted provider in B_02.02) or
**indirectly** (it appears at rank ≥ 2 in the B_05.02 supply chain of an arrangement that
supports the function). Both matter for DORA Art. 28/29: a hyperscaler that is a
subcontractor of ten SaaS vendors is a single point of failure for all of them.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from dora_roi.model import Function, RegisterOfInformation


@dataclass
class ImpactedFunction:
    function: Function
    entity_name: str
    direct_contracts: set[str] = field(default_factory=set)
    indirect_contracts: set[str] = field(default_factory=set)
    via: set[str] = field(default_factory=set)  # direct providers through which it depends
    #: Exit plan status of the affected ICT services (True/False per assessed service).
    exit_plans: list[bool] = field(default_factory=list)

    @property
    def exit_plan(self) -> bool | None:
        """True when every assessed affected service has an exit plan, None if none assessed."""
        return all(self.exit_plans) if self.exit_plans else None

    @property
    def is_direct(self) -> bool:
        return bool(self.direct_contracts)


@dataclass
class FailureImpact:
    provider_code: str
    functions: list[ImpactedFunction]
    entities: set[str]

    @property
    def critical(self) -> list[ImpactedFunction]:
        return [f for f in self.functions if f.function.is_critical]

    @property
    def critical_direct(self) -> int:
        return sum(1 for f in self.critical if f.is_direct)

    @property
    def critical_indirect_only(self) -> int:
        return sum(1 for f in self.critical if not f.is_direct)

    @property
    def shortest_rto(self) -> int | None:
        values = [f.function.rto_hours for f in self.critical if f.function.rto_hours is not None]
        return min(values) if values else None


def failure_impact(register: RegisterOfInformation, provider_code: str) -> FailureImpact:
    """Functions and entities affected if ``provider_code`` becomes unavailable."""
    functions = register.function_lookup()
    entities = register.entities_by_lei()
    providers = register.providers_by_code()
    via_contract: dict[str, set[str]] = defaultdict(set)
    for e in register.b_05_02:
        if e.provider_code == provider_code and (e.rank or 0) > 1 and e.contract_ref:
            via_contract[e.contract_ref].add(e.recipient_code or "")
    assessments = register.assessments_by_key()
    impacted: dict[tuple[str, str], ImpactedFunction] = {}
    affected_entities: set[str] = set()
    for s in register.b_02_02:
        if not (s.contract_ref and s.function_id and s.entity_lei):
            continue
        direct = s.provider_code == provider_code
        indirect = s.contract_ref in via_contract
        if not (direct or indirect):
            continue
        fn = functions.get((s.function_id, s.entity_lei))
        if fn is None:
            continue
        key = (s.function_id, s.entity_lei)
        item = impacted.get(key)
        if item is None:
            ent = entities.get(s.entity_lei)
            item = impacted[key] = ImpactedFunction(fn, (ent.name if ent and ent.name
                                                         else s.entity_lei))
        affected_entities.add(s.entity_lei)
        assessment = assessments.get((s.contract_ref, s.provider_code, s.service_type))
        if assessment is not None and assessment.exit_plan is not None:
            item.exit_plans.append(assessment.exit_plan)
        if direct:
            item.direct_contracts.add(s.contract_ref)
        if indirect:
            item.indirect_contracts.add(s.contract_ref)
            direct_name = providers.get(s.provider_code or "")
            item.via.add(direct_name.legal_name if direct_name and direct_name.legal_name
                         else s.provider_code or "")
    ordered = sorted(impacted.values(), key=lambda i: (not i.function.is_critical,
                                                       not i.is_direct,
                                                       i.function.function_id or ""))
    return FailureImpact(provider_code, ordered, affected_entities)
