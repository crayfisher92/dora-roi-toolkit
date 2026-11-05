"""Deterministic generator of a realistic synthetic register for the fictional *Alpenrand* group.

The group consists of a Swiss holding (outside the register scope) and three EU entities in
scope: a German credit institution maintaining the register on a sub-consolidated basis, a
Luxembourg private bank with a Paris branch and an Austrian UCITS management company. The
generator produces ~45 ICT third-party providers (including three fictional hyperscaler
groups), ~120 contractual arrangements with master agreements and call-offs, subcontracting
chains up to rank 3 and assessments/exit plans – and, optionally, a set of deliberately
injected errors documented in :attr:`SampleResult.injected`.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from dora_roi.io.parse import parse_raw
from dora_roi.io.raw import RawRegister, RawRow, RawTable
from dora_roi.lei import make_lei
from dora_roi.model import (
    TEMPLATE_MODELS,
    Branch,
    ContractGeneral,
    ContractSigningEntity,
    ContractSigningProvider,
    ContractSpecific,
    ContractType,
    Criticality,
    DataSensitivity,
    EntityInScope,
    EntityMaintainingRegister,
    Function,
    HierarchyInGroup,
    IctServiceType,
    IctThirdPartyProvider,
    Impact,
    NonSubstitutabilityReason,
    PersonType,
    ProviderCodeType,
    RegisterOfInformation,
    Reintegration,
    RelianceLevel,
    ServiceAssessment,
    ServiceRecipient,
    Substitutability,
    SupplyChainEntry,
    TerminationReason,
)
from dora_roi.model.codelists import AdditionalCodeType
from dora_roi.model.refdata import EEA_COUNTRIES
from dora_roi.model.types import INDEFINITE_END_DATE
from dora_roi.sample.catalogue import (
    HOLDING_NAME,
    Catalogue,
    EntitySpec,
    FunctionSpec,
    OfferingSpec,
    ProviderSpec,
)
from dora_roi.validation import Finding

DEFAULT_SEED = 2554
DEFAULT_REFERENCE_DATE = date(2025, 12, 31)
_LOU_PREFIXES = ("5299", "3912", "8156", "9845", "2138", "6354", "8945", "7245")
_ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_HYPERSCALER_DATA = {"nimbus_eu": "DE", "stratus_eu": "LU", "cirrus_eu": "IE",
                     "nimbus_us": "US", "stratus_us": "US", "cirrus_us": "US"}
_SENSITIVE = {"core", "payments", "aml", "pms", "custody", "cards", "lending", "fundacct",
              "digital", "crm", "hr", "clientrep"}


def synthetic_lei(name: str) -> str:
    """Deterministic, checksum-valid but fictional LEI derived from ``name``."""
    digest = hashlib.sha256(name.encode()).digest()
    prefix = _LOU_PREFIXES[digest[0] % len(_LOU_PREFIXES)]
    body = "".join(_ALNUM[b % 36] for b in digest[1:15])
    return make_lei(prefix + body)


@dataclass(frozen=True)
class InjectedError:
    """A deliberately introduced defect and the rule(s) expected to catch it."""

    rule_ids: tuple[str, ...]
    template: str
    record: str
    description: str


@dataclass
class SampleResult:
    #: Register as it would be written to a file (may contain deliberately invalid raw values).
    source_register: RegisterOfInformation
    #: Register after the round trip through the parser (invalid values dropped).
    register: RegisterOfInformation
    #: Field-level findings produced by the parser.
    findings: list[Finding]
    injected: list[InjectedError] = field(default_factory=list)
    reference_date: date = DEFAULT_REFERENCE_DATE


@dataclass
class _Ctx:
    rng: random.Random
    ref: date
    cat: Catalogue
    reg: RegisterOfInformation = field(default_factory=RegisterOfInformation)
    entity_lei: dict[str, str] = field(default_factory=dict)
    provider_code: dict[str, str] = field(default_factory=dict)
    provider_spec: dict[str, ProviderSpec] = field(default_factory=dict)
    functions: dict[tuple[str, str], tuple[str, FunctionSpec]] = field(default_factory=dict)
    provider_cost: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    counter: int = 0
    critical_contracts: set[str] = field(default_factory=set)


# --------------------------------------------------------------------------- building blocks


def _rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _build_entities(ctx: _Ctx) -> None:
    holding = synthetic_lei(HOLDING_NAME)
    for spec in ctx.cat.entities:
        ctx.entity_lei[spec.key] = synthetic_lei(spec.name)
    for spec in ctx.cat.entities:
        _add_entity(ctx, spec, holding)
    de = ctx.cat.entities[0]
    ctx.reg.add(EntityMaintainingRegister(
        lei=ctx.entity_lei[de.key], name=de.name, country=de.country, entity_type=de.entity_type,
        competent_authority=de.authority, reporting_date=ctx.ref))


def _add_entity(ctx: _Ctx, spec: EntitySpec, holding: str) -> None:
    lei = ctx.entity_lei[spec.key]
    is_eu_parent = spec.parent is None
    ctx.reg.add(EntityInScope(
        lei=lei, name=spec.name, country=spec.country, entity_type=spec.entity_type,
        hierarchy=HierarchyInGroup.PARENT if is_eu_parent else HierarchyInGroup.SUBSIDIARY,
        parent_lei=holding if is_eu_parent else ctx.entity_lei[spec.parent or ""],
        last_update=ctx.ref - timedelta(days=ctx.rng.randint(5, 40)),
        integration_date=date(ctx.ref.year, 1, 17), currency="EUR",
        total_assets=Decimal(spec.total_assets)))
    for code, name, country in spec.branches:
        ctx.reg.add(Branch(branch_code=code, head_office_lei=lei, name=name, country=country))
    for i, fn in enumerate(ctx.cat.functions[spec.key], start=1):
        fid = f"F-{spec.key}-{i:02d}"
        ctx.functions[(spec.key, fn.capability)] = (fid, fn)
        ctx.reg.add(Function(
            function_id=fid, licensed_activity=fn.activity, function_name=fn.name,
            entity_lei=lei,
            criticality=Criticality.CRITICAL if fn.critical else Criticality.NOT_CRITICAL,
            criticality_reasons=(f"Disruption of {fn.name.lower()} would materially impair the "
                                 "continuity of regulated services or compliance")
            if fn.critical else None,
            last_assessment_date=_rand_date(ctx.rng, ctx.ref - timedelta(days=300),
                                            ctx.ref - timedelta(days=20)),
            rto_hours=fn.rto if fn.critical else None,
            rpo_hours=fn.rpo if fn.critical else None,
            discontinuation_impact=Impact.HIGH if fn.critical else
            ctx.rng.choice([Impact.LOW, Impact.MEDIUM])))


def _build_providers(ctx: _Ctx) -> None:
    for spec in ctx.cat.providers:
        ctx.provider_spec[spec.key] = spec
        ctx.provider_code[spec.key] = (spec.euid if spec.code_type == "EUID" and spec.euid
                                       else synthetic_lei(spec.name))


def _finalise_providers(ctx: _Ctx) -> None:
    for spec in ctx.cat.providers:
        code = ctx.provider_code[spec.key]
        parent_key = spec.parent or spec.key
        parent_spec = ctx.provider_spec[parent_key]
        cost = ctx.provider_cost.get(code, Decimal(0))
        uplift = Decimal(str(round(1 + ctx.rng.uniform(0.02, 0.25), 3)))
        ctx.reg.add(IctThirdPartyProvider(
            provider_code=code,
            provider_code_type=ProviderCodeType(spec.code_type),
            additional_code=spec.additional[0] if spec.additional else None,
            additional_code_type=AdditionalCodeType(spec.additional[1])
            if spec.additional else None,
            legal_name=spec.name,
            latin_name=spec.latin_name,
            person_type=PersonType.LEGAL,
            hq_country=spec.country,
            currency="EUR",
            total_annual_cost=(cost * uplift).quantize(Decimal(1000)) if cost else
            Decimal(ctx.rng.randint(20, 80) * 1000),
            ultimate_parent_code=ctx.provider_code[parent_key],
            ultimate_parent_code_type=ProviderCodeType(parent_spec.code_type),
        ))


def _data_location(ctx: _Ctx, offering: OfferingSpec, entity: EntitySpec) -> str:
    host = offering.hosted_on or offering.provider
    if host in _HYPERSCALER_DATA:
        return _HYPERSCALER_DATA[host]
    country = ctx.provider_spec[host].country
    return country if country in EEA_COUNTRIES or country in ("CH", "GB", "US") else entity.country


def _new_ref(ctx: _Ctx, prefix: str) -> str:
    ctx.counter += 1
    return f"{prefix}-{ctx.counter:04d}"


def _add_contract(ctx: _Ctx, offering: OfferingSpec, entity: EntitySpec,
                  fns: list[tuple[str, FunctionSpec]], contract_type: ContractType,
                  overarching: str | None = None, ref: str | None = None,
                  signer: EntitySpec | None = None) -> str:
    rng = ctx.rng
    pspec = ctx.provider_spec[offering.provider]
    pcode = ctx.provider_code[offering.provider]
    lei = ctx.entity_lei[entity.key]
    prefix = {ContractType.OVERARCHING: "MSA", ContractType.SUBSEQUENT: "CO"}.get(
        contract_type, "AR")
    ref = ref or _new_ref(ctx, f"{prefix}-{entity.key}")
    cost = Decimal(rng.randint(offering.cost[0] // 1000, offering.cost[1] // 1000) * 1000)
    if entity.key == "AT":
        cost = (cost * Decimal("0.35")).quantize(Decimal(1000))
    ctx.reg.add(ContractGeneral(contract_ref=ref, contract_type=contract_type,
                                overarching_ref=overarching, currency="EUR", annual_cost=cost))
    ctx.provider_cost[pcode] += cost
    start = _rand_date(rng, date(2015, 1, 1), date(2025, 6, 30))
    end = INDEFINITE_END_DATE if rng.random() < 0.6 else _rand_date(
        rng, date(2026, 2, 1), date(2030, 12, 31))
    governing = pspec.country if pspec.country in EEA_COUNTRIES | {"CH"} else entity.country
    service_country = pspec.country if pspec.key not in _HYPERSCALER_DATA else (
        "US" if pspec.country == "US" else pspec.country)
    data_loc = _data_location(ctx, offering, entity) if offering.data else None
    any_critical = False
    for fid, fn in fns:
        any_critical |= fn.critical
        ctx.reg.add(ContractSpecific(
            contract_ref=ref, entity_lei=lei, provider_code=pcode,
            provider_code_type=ProviderCodeType(pspec.code_type), function_id=fid,
            service_type=offering.service, start_date=start, end_date=end,
            notice_period_entity=rng.choice([30, 60, 90, 180]),
            notice_period_provider=rng.choice([90, 180, 365]),
            governing_law_country=governing, service_country=service_country,
            data_storage=offering.data,
            data_location_storage=data_loc,
            data_location_processing=data_loc if offering.data else None,
            data_sensitivity=(DataSensitivity.HIGH if fn.capability in _SENSITIVE
                              else DataSensitivity.MEDIUM) if offering.data else None,
            reliance_level=RelianceLevel(offering.reliance) if fn.critical
            else rng.choice([RelianceLevel.LOW, RelianceLevel.MATERIAL]),
        ))
    sign = signer or entity
    ctx.reg.add(ContractSigningEntity(contract_ref=ref, entity_lei=ctx.entity_lei[sign.key]))
    ctx.reg.add(ContractSigningProvider(contract_ref=ref, provider_code=pcode,
                                        provider_code_type=ProviderCodeType(pspec.code_type)))
    ctx.reg.add(ServiceRecipient(contract_ref=ref, entity_lei=lei, is_branch=False))
    caps = {fn.capability for _, fn in fns}
    if entity.branches and caps & {"payments", "core", "crm", "workplace"} and rng.random() < 0.5:
        ctx.reg.add(ServiceRecipient(contract_ref=ref, entity_lei=lei, is_branch=True,
                                     branch_code=entity.branches[0][0]))
    if any_critical:
        ctx.critical_contracts.add(ref)
    if any_critical or offering.hosted_on:
        _add_chain(ctx, ref, offering)
    if any_critical or rng.random() < 0.5:
        _add_assessment(ctx, ref, offering, any_critical)
    return ref


def _add_chain(ctx: _Ctx, ref: str, offering: OfferingSpec) -> None:
    def entry(key: str, rank: int, recipient: str | None) -> SupplyChainEntry:
        spec = ctx.provider_spec[key]
        rspec = ctx.provider_spec[recipient] if recipient else None
        return SupplyChainEntry(
            contract_ref=ref, service_type=offering.service,
            provider_code=ctx.provider_code[key],
            provider_code_type=ProviderCodeType(spec.code_type), rank=rank,
            recipient_code=ctx.provider_code[recipient] if recipient else None,
            recipient_code_type=ProviderCodeType(rspec.code_type) if rspec else None)

    ctx.reg.add(entry(offering.provider, 1, None))
    if offering.hosted_on:
        ctx.reg.add(entry(offering.hosted_on, 2, offering.provider))
        if offering.rank3:
            ctx.reg.add(entry(offering.rank3, 3, offering.hosted_on))


def _add_assessment(ctx: _Ctx, ref: str, offering: OfferingSpec, critical: bool) -> None:
    rng = ctx.rng
    spec = ctx.provider_spec[offering.provider]
    sub = offering.substitutability
    hard = sub.is_hard
    alternatives = sub is not Substitutability.NOT_SUBSTITUTABLE
    ctx.reg.add(ServiceAssessment(
        contract_ref=ref, provider_code=ctx.provider_code[offering.provider],
        provider_code_type=ProviderCodeType(spec.code_type), service_type=offering.service,
        substitutability=sub,
        non_substitutability_reason=(NonSubstitutabilityReason.BOTH
                                     if sub is Substitutability.NOT_SUBSTITUTABLE
                                     else NonSubstitutabilityReason.MIGRATION) if hard else None,
        last_audit_date=_rand_date(rng, ctx.ref - timedelta(days=900),
                                   ctx.ref - timedelta(days=30))
        if critical or rng.random() < 0.4 else None,
        exit_plan=True if critical else rng.random() < 0.5,
        reintegration=Reintegration.HIGHLY_COMPLEX if hard else
        rng.choice([Reintegration.EASY, Reintegration.DIFFICULT]),
        discontinuation_impact=Impact.HIGH if critical and hard else
        Impact.MEDIUM if critical else Impact.LOW,
        alternatives_identified=alternatives,
        alternative_providers="Two alternative providers short-listed in the exit plan"
        if alternatives else None,
    ))


def _build_contracts(ctx: _Ctx) -> None:
    entities = {e.key: e for e in ctx.cat.entities}
    de = ctx.cat.entities[0]
    for offering in ctx.cat.offerings:
        targets = offering.entities or tuple(entities)
        matches: dict[str, list[tuple[str, FunctionSpec]]] = {}
        for key in targets:
            fns = [ctx.functions[(key, cap)] for cap in offering.capabilities
                   if (key, cap) in ctx.functions]
            if fns:
                matches[key] = fns
        if not matches:
            continue
        if offering.group_master:
            msa = _new_ref(ctx, f"MSA-{de.key}")
            _add_contract(ctx, offering, de, matches.get(de.key) or [
                next(iter(matches.values()))[0]], ContractType.OVERARCHING, ref=msa)
            for key, fns in matches.items():
                if key != de.key:
                    _add_contract(ctx, offering, entities[key], fns, ContractType.SUBSEQUENT,
                                  overarching=msa)
            continue
        for key, fns in matches.items():
            # large application estates are split into licence/maintenance per function group
            if len(fns) >= 2 and ctx.rng.random() < 0.85:
                half = len(fns) // 2
                _add_contract(ctx, offering, entities[key], fns[:half], ContractType.STANDALONE)
                _add_contract(ctx, offering, entities[key], fns[half:], ContractType.STANDALONE)
            else:
                _add_contract(ctx, offering, entities[key], fns, ContractType.STANDALONE)


def _terminate_some(ctx: _Ctx) -> None:
    """Mark two non-critical arrangements as ended during the reference year."""
    candidates = sorted({s.contract_ref for s in ctx.reg.b_02_02
                         if s.contract_ref and s.contract_ref not in ctx.critical_contracts
                         and s.contract_ref.startswith("AR-")})
    for ref, end in zip(candidates[3:5], (date(2025, 6, 30), date(2025, 9, 30)), strict=False):
        for s in ctx.reg.b_02_02:
            if s.contract_ref == ref:
                s.end_date = end
                s.termination_reason = TerminationReason.EXPIRED


# --------------------------------------------------------------------------- error injection


def _inject(ctx: _Ctx) -> list[InjectedError]:
    reg = ctx.reg
    out: list[InjectedError] = []

    def note(rules: tuple[str, ...], template: str, record: str, text: str) -> None:
        out.append(InjectedError(rules, template, record, text))

    crit = [s for s in reg.b_02_02 if s.contract_ref in ctx.critical_contracts]
    non_crit = [s for s in reg.b_02_02 if s.contract_ref not in ctx.critical_contracts
                and s.contract_ref and s.contract_ref.startswith("AR-")]
    by_provider = {p.legal_name: p for p in reg.b_05_01}

    # 1. typo in a provider LEI on one arrangement row
    s = non_crit[0]
    bad = (s.provider_code or "")[:-2] + ("00" if not (s.provider_code or "").endswith("00")
                                          else "11")
    s.provider_code = bad
    note(("FLD-013", "XRF-003"), "B_02.02", s.key_str(),
         "Provider LEI on one arrangement row has wrong check digits (typo)")
    # 2. "UK" instead of "GB" as governing law
    veritas = by_provider["Veritas KYC Solutions Ltd"].provider_code
    s = next(x for x in reg.b_02_02 if x.provider_code == veritas)
    s.governing_law_country = "GB"
    s.service_country = "GB"
    setattr(s, "governing_law_country", "UK")  # noqa: B010 - bypasses typing on purpose
    note(("FLD-005",), "B_02.02", s.key_str(), "Governing law country reported as 'UK'")
    # 3. currency spelled out
    c = next(x for x in reg.b_02_01 if x.contract_ref == non_crit[1].contract_ref)
    setattr(c, "currency", "EURO")  # noqa: B010
    note(("FLD-006",), "B_02.01", c.key_str(), "Currency reported as 'EURO'")
    # 4. date in DD/MM/YYYY format
    s = non_crit[2]
    setattr(s, "end_date", "31/12/2027")  # noqa: B010
    note(("FLD-003",), "B_02.02", s.key_str(), "End date in DD/MM/YYYY format")
    # 5. ICT service type outside the taxonomy
    s = non_crit[4]
    setattr(s, "service_type", "S20")  # noqa: B010
    note(("FLD-004",), "B_02.02", s.key_str(), "ICT service type 'S20' does not exist")
    # 6. mandatory governing law missing
    s = non_crit[6]
    s.governing_law_country = None
    note(("FLD-001",), "B_02.02", s.key_str(), "Governing law country left empty")
    # 7. end date before start date
    s = non_crit[8]
    s.start_date, s.end_date = date(2024, 5, 1), date(2023, 4, 30)
    note(("BUS-001",), "B_02.02", s.key_str(), "End date precedes start date")
    # 8. ended arrangement without termination reason
    s = non_crit[10]
    s.end_date = date(2025, 10, 31)
    s.termination_reason = None
    note(("BUS-002",), "B_02.02", s.key_str(), "Arrangement ended in 2025 without reason")
    # 9. data stored but no location
    s = next(x for x in crit if x.data_storage)
    s.data_location_storage = None
    note(("BUS-004",), "B_02.02", s.key_str(), "Data storage = true but no storage location")
    # 10. function identifier typo
    s = crit[3]
    s.function_id = (s.function_id or "").replace("-0", "-")
    note(("XRF-004",), "B_02.02", s.key_str(),
         "Function identifier typo (leading zero dropped, e.g. F-LU-1 for F-LU-01)")
    # 11. arrangement with a provider missing from B_05.01 ("shadow IT")
    shadow = synthetic_lei("Shadow Analytics Startup GmbH")
    template_row = non_crit[12]
    reg.add(ContractGeneral(contract_ref="AR-DE-9001", contract_type=ContractType.STANDALONE,
                            currency="EUR", annual_cost=Decimal(45000)))
    reg.add(template_row.model_copy(update={"contract_ref": "AR-DE-9001",
                                            "provider_code": shadow}))
    reg.add(ContractSigningEntity(contract_ref="AR-DE-9001",
                                  entity_lei=template_row.entity_lei))
    reg.add(ServiceRecipient(contract_ref="AR-DE-9001", entity_lei=template_row.entity_lei,
                             is_branch=False))
    note(("XRF-003", "XRF-008"), "B_02.02", "AR-DE-9001",
         "Arrangement with a provider that is not listed in B_05.01 (shadow IT)")
    # 12. duplicate arrangement reference
    dup = reg.b_02_01[5].model_copy()
    reg.add(dup)
    note(("FLD-010",), "B_02.01", dup.key_str(), "Arrangement reference reported twice")
    # 13. arrangement without any B_02.02 row
    reg.add(ContractGeneral(contract_ref="AR-LU-9002", contract_type=ContractType.STANDALONE,
                            currency="EUR", annual_cost=Decimal(12000)))
    reg.add(ContractSigningEntity(contract_ref="AR-LU-9002", entity_lei=ctx.entity_lei["LU"]))
    reg.add(ServiceRecipient(contract_ref="AR-LU-9002", entity_lei=ctx.entity_lei["LU"],
                             is_branch=False))
    note(("XRF-006",), "B_02.01", "AR-LU-9002", "Arrangement without specific information")
    # 14. B_04.01 referencing an unknown arrangement
    reg.add(ServiceRecipient(contract_ref="AR-AT-0000", entity_lei=ctx.entity_lei["AT"],
                             is_branch=False))
    note(("XRF-001",), "B_04.01", "AR-AT-0000", "Service recipient for an unknown arrangement")
    # 15. entity LEI with wrong check digits in B_03.01
    sig = reg.b_03_01[7]
    lei = sig.entity_lei or ""
    setattr(sig, "entity_lei", lei[:-2] + ("99" if not lei.endswith("99") else "98"))  # noqa: B010
    note(("FLD-002",), "B_03.01", sig.key_str(), "Signing entity LEI with wrong check digits")
    # 16/17. critical services without exit plan
    crit_assessments = [a for a in reg.b_07_01 if a.contract_ref in ctx.critical_contracts]
    for a in crit_assessments[2:4]:
        a.exit_plan = False
        note(("BUS-019",), "B_07.01", a.key_str(),
             "ICT service supporting a critical function without exit plan")
    # 18. not substitutable without reason
    a = next(x for x in reg.b_07_01 if x.substitutability is Substitutability.NOT_SUBSTITUTABLE)
    a.non_substitutability_reason = None
    note(("BUS-020",), "B_07.01", a.key_str(), "'Not substitutable' without a reason")
    # 19. critical service without any assessment
    victim = crit_assessments[6]
    reg.b_07_01.remove(victim)
    note(("BUS-018",), "B_07.01", victim.key_str(),
         "Assessment of an ICT service supporting a critical function is missing")
    # 20. critical function without RTO
    f = next(x for x in reg.b_06_01 if x.is_critical and x.function_id == "F-LU-05")
    f.rto_hours = None
    note(("BUS-015",), "B_06.01", f.key_str(), "Critical function without RTO")
    # 21. broken subcontracting chain (rank 3 recipient not at rank 2)
    rank3 = next(e for e in reg.b_05_02 if e.rank == 3)
    rank3.recipient_code = ctx.provider_code["luxhost"]
    note(("SC-003",), "B_05.02", rank3.key_str(),
         "Rank 3 subcontractor points to a recipient that is not at rank 2")
    # 22. rank 1 provider that is not the direct provider
    rank1 = next(e for e in reg.b_05_02 if e.rank == 1 and e.contract_ref != rank3.contract_ref)
    rank1.provider_code = ctx.provider_code["netwave"]
    rank1.provider_code_type = ProviderCodeType.LEI
    note(("SC-001",), "B_05.02", rank1.key_str(),
         "Rank 1 of a supply chain is not the arrangement's direct provider")
    # 23. amount in CHF (warning)
    c = next(x for x in reg.b_02_01 if x.contract_ref and x.contract_ref.startswith("AR-LU"))
    c.currency = "CHF"
    note(("BUS-008",), "B_02.01", c.key_str(), "Amount in CHF instead of the reporting currency")
    # 24. stale provider not used by any arrangement (warning)
    reg.add(IctThirdPartyProvider(
        provider_code=synthetic_lei("Legacy Mainframe Services GmbH"),
        provider_code_type=ProviderCodeType.LEI, legal_name="Legacy Mainframe Services GmbH",
        person_type=PersonType.LEGAL, hq_country="DE", currency="EUR",
        total_annual_cost=Decimal(0),
        ultimate_parent_code=synthetic_lei("Legacy Mainframe Services GmbH"),
        ultimate_parent_code_type=ProviderCodeType.LEI))
    note(("XRF-010",), "B_05.01", "Legacy Mainframe Services GmbH",
         "Provider decommissioned but still listed")
    # 25. criticality not assessed (warning)
    f = next(x for x in reg.b_06_01 if not x.is_critical and x.function_id == "F-AT-06")
    f.criticality = Criticality.NOT_ASSESSED
    note(("BUS-016",), "B_06.01", f.key_str(), "Function never assessed for criticality")
    return out


# --------------------------------------------------------------------------- public API


def register_to_raw(register: RegisterOfInformation, source: str = "sample") -> RawRegister:
    """Serialise a (possibly dirty) register to raw text tables, as a file would contain."""
    raw = RawRegister(source=source)
    for model in TEMPLATE_MODELS:
        rows = [RawRow(row=i, values=dict(rec.to_row()))
                for i, rec in enumerate(register.records(model.TEMPLATE), start=4)]
        raw.tables[model.TEMPLATE] = RawTable(model.TEMPLATE, [c.code for c in model.columns()],
                                              rows, source=f"{source}:{model.TEMPLATE}")
    return raw


def generate_sample(
    seed: int = DEFAULT_SEED,
    inject_errors: bool = True,
    reference_date: date = DEFAULT_REFERENCE_DATE,
    catalogue: Catalogue | None = None,
) -> SampleResult:
    """Generate the synthetic Alpenrand register.

    The output is fully deterministic for a given ``seed``.
    """
    # bandit B311: synthetic data, not security
    ctx = _Ctx(rng=random.Random(seed), ref=reference_date, cat=catalogue or Catalogue())  # nosec B311
    _build_entities(ctx)
    _build_providers(ctx)
    _build_contracts(ctx)
    _terminate_some(ctx)
    _finalise_providers(ctx)
    injected = _inject(ctx) if inject_errors else []
    parsed = parse_raw(register_to_raw(ctx.reg, "alpenrand-sample"))
    return SampleResult(ctx.reg, parsed.register, parsed.findings, injected, reference_date)


PREVIOUS_REFERENCE_DATE = date(2024, 12, 31)


def generate_previous_year(seed: int = DEFAULT_SEED) -> SampleResult:
    """The Alpenrand register as it stood one year earlier (for the register diff demo).

    Compared with the current clean sample: arrangements that started in 2025 did not exist
    yet, the two arrangements that ended in 2025 were still running, a mainframe provider that
    has since been exited was still in place, and annual costs were about 8 % lower.
    """
    # bandit B311: synthetic data, not security
    ctx = _Ctx(rng=random.Random(seed), ref=PREVIOUS_REFERENCE_DATE, cat=Catalogue())  # nosec B311
    _build_entities(ctx)
    _build_providers(ctx)
    _build_contracts(ctx)
    reg = ctx.reg
    new_refs = {s.contract_ref for s in reg.b_02_02
                if s.start_date and s.start_date > PREVIOUS_REFERENCE_DATE}
    for model in TEMPLATE_MODELS:
        records = reg.records(model.TEMPLATE)
        if "contract_ref" in model.model_fields:
            records[:] = [r for r in records
                          if getattr(r, "contract_ref") not in new_refs]  # noqa: B009
    for c in reg.b_02_01:
        if c.annual_cost is not None:
            c.annual_cost = (c.annual_cost * Decimal("0.92")).quantize(Decimal(1000))
    ctx.provider_cost.clear()
    for ref, providers in _direct_providers(reg).items():
        cost = next((c.annual_cost for c in reg.b_02_01 if c.contract_ref == ref), None)
        for code in providers:
            ctx.provider_cost[code] += cost or Decimal(0)
    # an exited mainframe outsourcing arrangement
    legacy = ProviderSpec("legacy", "Legacy Mainframe Services GmbH", "DE")
    ctx.provider_spec[legacy.key] = legacy
    ctx.provider_code[legacy.key] = synthetic_lei(legacy.name)
    ctx.cat = Catalogue(providers=(*ctx.cat.providers, legacy))
    de = ctx.cat.entities[0]
    _add_contract(ctx, OfferingSpec("legacy", IctServiceType.S14, ("core",), (400_000, 400_000),
                                    Substitutability.MEDIUM, data=True), de,
                  [ctx.functions[("DE", "core")]], ContractType.STANDALONE, ref="AR-DE-0999")
    for s in reg.b_02_02:
        if s.contract_ref == "AR-DE-0999":
            s.end_date = date(2025, 3, 31)
    used = {s.provider_code for s in reg.b_02_02} | {e.provider_code for e in reg.b_05_02}
    _finalise_providers(ctx)
    reg.b_05_01[:] = [p for p in reg.b_05_01 if p.provider_code in used
                      or any(q.ultimate_parent_code == p.provider_code for q in reg.b_05_01
                             if q.provider_code in used)]
    parsed = parse_raw(register_to_raw(reg, "alpenrand-2024"))
    return SampleResult(reg, parsed.register, parsed.findings, [], PREVIOUS_REFERENCE_DATE)


def _direct_providers(reg: RegisterOfInformation) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for s in reg.b_02_02:
        if s.contract_ref and s.provider_code:
            out[s.contract_ref].add(s.provider_code)
    return dict(out)
