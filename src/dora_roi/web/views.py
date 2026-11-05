"""View models assembled for the web templates (kept out of the route handlers)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from dora_roi.analytics import ProviderExposure
from dora_roi.analytics.impact import FailureImpact, failure_impact
from dora_roi.model import (
    ContractSpecific,
    Function,
    IctThirdPartyProvider,
    ServiceAssessment,
    serialise_value,
)
from dora_roi.model.refdata import country_name, region_of
from dora_roi.model.types import INDEFINITE_END_DATE
from dora_roi.validation import Finding
from dora_roi.workspace import Workspace

STEPS = ("import", "fix", "analyse", "export")


@dataclass(frozen=True)
class Step:
    key: str
    state: str  # done | current | todo
    href: str


def stepper(ws: Workspace, current: str) -> list[Step]:
    errors = ws.report.severity_counts()["error"]
    done = {"import"}
    if errors == 0:
        done.add("fix")
    if "analyse" in ws.visited:
        done.add("analyse")
    if "export" in ws.visited:
        done.add("export")
    hrefs = {"import": f"/w/{ws.id}", "fix": f"/w/{ws.id}/fix",
             "analyse": f"/w/{ws.id}/analyse", "export": f"/w/{ws.id}/export"}
    out = []
    for key in STEPS:
        state = "current" if key == current else ("done" if key in done else "todo")
        out.append(Step(key, state, hrefs[key]))
    return out


@dataclass(frozen=True)
class Flag:
    level: str  # high | medium
    text: str


@dataclass
class ProviderProfile:
    provider: IctThirdPartyProvider | None
    code: str
    name: str
    exposure: ProviderExposure | None
    group_name: str
    services: list[ContractSpecific] = field(default_factory=list)
    functions: list[tuple[Function, int]] = field(default_factory=list)
    assessments: list[ServiceAssessment] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    impact: FailureImpact | None = None
    findings: list[Finding] = field(default_factory=list)
    spend: Decimal = Decimal(0)
    share: float = 0.0


def provider_profile(ws: Workspace, code: str, t: Callable[..., str]) -> ProviderProfile:
    reg = ws.register
    a = ws.analysis
    provider = reg.providers_by_code().get(code)
    exposure = next((p for p in a.providers if p.code == code), None)
    name = (provider.legal_name if provider and provider.legal_name else
            exposure.name if exposure else code)
    group = exposure.group_name if exposure else name
    profile = ProviderProfile(provider, code, name, exposure, group)
    profile.impact = failure_impact(reg, code)
    profile.services = [s for s in reg.b_02_02 if s.provider_code == code]
    fl = reg.function_lookup()
    counts: dict[tuple[str, str], int] = {}
    for s in profile.services:
        key = (s.function_id or "", s.entity_lei or "")
        counts[key] = counts.get(key, 0) + 1
    profile.functions = sorted(((fl[k], n) for k, n in counts.items() if k in fl),
                               key=lambda fn: (not fn[0].is_critical, fn[0].function_id or ""))
    profile.assessments = [x for x in reg.b_07_01 if x.provider_code == code]
    if exposure:
        profile.spend = exposure.spend
        profile.share = exposure.spend_share
    impact = profile.impact
    if impact.critical:
        profile.flags.append(Flag("high", t(
            "prov.flag.impact", n=len(impact.critical), d=impact.critical_direct,
            i=impact.critical_indirect_only, e=len(impact.entities),
            rto=impact.shortest_rto if impact.shortest_rto is not None else "—")))
    if exposure:
        if exposure.hard_to_substitute:
            profile.flags.append(Flag("high", t("prov.flag.hard")))
        if exposure.critical_services_without_exit_plan:
            profile.flags.append(Flag("high", t("prov.flag.no_exit",
                                                n=exposure.critical_services_without_exit_plan)))
        if exposure.subcontractor_appearances:
            profile.flags.append(Flag("medium", t("prov.flag.subcontractor",
                                                  n=exposure.subcontractor_appearances)))
    group_provider = reg.providers_by_code().get(
        provider.ultimate_parent_code or "" if provider else "")
    group_country = (group_provider.hq_country if group_provider else
                     provider.hq_country if provider else None)
    if region_of(group_country) == "Third country":
        profile.flags.append(Flag("medium", t("prov.flag.third",
                                              country=country_name(group_country))))
    for e in a.expiring_critical:
        if any(s.contract_ref == e.contract_ref for s in profile.services):
            profile.flags.append(Flag("medium", t("prov.flag.expiring", ref=e.contract_ref,
                                                  days=e.days_left)))
    if exposure and exposure.critical_functions and profile.assessments and all(
            x.last_audit_date is None for x in profile.assessments):
        profile.flags.append(Flag("medium", t("prov.flag.no_audit")))
    keys = {s.key_str() for s in profile.services} | {x.key_str() for x in profile.assessments}
    profile.findings = [f for f in ws.report.findings
                        if (f.record_key in keys) or (f.value == code)
                        or (provider is not None and f.template == "B_05.01"
                            and f.row == provider.row)]
    return profile


def display(value: Any) -> str:
    """Human display of a raw or typed value."""
    if value is None:
        return ""
    if value == INDEFINITE_END_DATE:
        return "9999-12-31"
    text = serialise_value(value)
    return text if text is not None else ""

