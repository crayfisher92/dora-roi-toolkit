"""Consistency hints between what the register reports and what the contract contains.

The register (B_02.02, B_05.02, B_07.01) states facts that normally come from the contract –
notice periods, locations, subcontractors, an exit plan, audits. When the Art. 30 assessment
says the corresponding clause is missing, one of the two is probably wrong (or the fact is
not contractually secured). These hints are prompts for the reviewer, not findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dora_roi.contracts.analysis import ContractCompliance
from dora_roi.contracts.model import ProvisionStatus
from dora_roi.model import RegisterOfInformation


@dataclass(frozen=True)
class Hint:
    provision_id: str
    key: str  # i18n key "c30.hint.<key>"
    params: dict[str, object] = field(default_factory=dict)


def consistency_hints(register: RegisterOfInformation, c: ContractCompliance) -> list[Hint]:
    ref = c.ref
    status = {i.provision.id: i.status for i in c.items}
    gap = (ProvisionStatus.MISSING, ProvisionStatus.PARTIAL)
    rows = [s for s in register.b_02_02 if s.contract_ref == ref]
    hints: list[Hint] = []
    if status.get("30.2.h") in gap:
        periods = sorted({(s.notice_period_entity, s.notice_period_provider) for s in rows
                          if s.notice_period_entity is not None
                          or s.notice_period_provider is not None},
                         key=lambda x: (x[0] or 0, x[1] or 0))
        if periods:
            ent, prov = periods[0]
            hints.append(Hint("30.2.h", "notice", {"entity": ent if ent is not None else "—",
                                                   "provider": prov if prov is not None
                                                   else "—"}))
    if status.get("30.2.b.1") is ProvisionStatus.MISSING:
        countries = sorted({x for s in rows for x in (s.service_country,
                                                      s.data_location_storage) if x})
        if countries:
            hints.append(Hint("30.2.b.1", "locations", {"countries": ", ".join(countries)}))
    if status.get("30.2.a.2") in gap:
        subs = {e.provider_code for e in register.b_05_02
                if e.contract_ref == ref and (e.rank or 0) >= 2 and e.provider_code}
        if subs:
            names = register.providers_by_code()
            listed = ", ".join(sorted(names[s].legal_name or s if s in names else s
                                      for s in subs))
            hints.append(Hint("30.2.a.2", "subcontractors", {"n": len(subs),
                                                             "names": listed}))
    exit_plan = any(a.exit_plan for a in register.b_07_01 if a.contract_ref == ref)
    if exit_plan and status.get("30.3.f.i") is ProvisionStatus.MISSING:
        hints.append(Hint("30.3.f.i", "exit_plan"))
    if status.get("30.3.e.i") is ProvisionStatus.PRESENT and c.context.critical:
        assessments = [a for a in register.b_07_01 if a.contract_ref == ref]
        if assessments and all(a.last_audit_date is None for a in assessments):
            hints.append(Hint("30.3.e.i", "no_audit"))
    return hints
