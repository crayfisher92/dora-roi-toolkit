"""ICT concentration-risk analytics on a register of information.

Supports the entity-level assessment of ICT concentration risk required by DORA Art. 29 and
the analysis of dependencies on ICT third-party service providers supporting critical or
important functions (Art. 28). The metrics are analytical aids for a GRC consultant; their
thresholds are heuristics documented in ``docs/ASSUMPTIONS.md`` (A-AN-*).

Conventions
-----------
* **Spend** is the annual cost of contractual arrangements (B_02.01 c0050) in the reporting
  currency. When an arrangement has several direct providers its cost is split equally.
  Amounts in other currencies are not converted; they are reported as excluded.
* **Provider group** = ultimate parent undertaking (B_05.01 c0110) – concentration on a
  hyperscaler is assessed across all of its legal entities.
* A **critical function** is a (function identifier, entity LEI) pair assessed as critical or
  important in B_06.01.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from dora_roi.model import (
    ContractSpecific,
    IctServiceType,
    IctThirdPartyProvider,
    RegisterOfInformation,
    ServiceAssessment,
    Substitutability,
)
from dora_roi.model.refdata import country_name, region_of
from dora_roi.model.types import INDEFINITE_END_DATE


@dataclass(frozen=True)
class AnalyticsConfig:
    """Thresholds used to turn metrics into key findings."""

    top_n: int = 10
    #: A provider group supporting at least this many critical functions is flagged.
    multi_cif_threshold: int = 3
    #: Spend share of a single provider group above which concentration is flagged.
    single_group_share_threshold: float = 0.25
    #: Herfindahl-Hirschman index (0-10 000) bands.
    hhi_moderate: float = 1500
    hhi_high: float = 2500
    #: Horizon for "arrangements supporting critical functions expiring soon".
    expiry_horizon_days: int = 365
    #: Subcontracting depth (max rank) considered deep.
    deep_chain_rank: int = 3
    reference_date: date | None = None


class Level(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class KeyFinding(BaseModel):
    level: Level
    title: str
    detail: str


class ProviderExposure(BaseModel):
    code: str
    name: str
    hq_country: str | None = None
    region: str = "Unknown"
    group_code: str
    group_name: str
    contracts: int = 0
    entities: int = 0
    functions: int = 0
    critical_functions: int = 0
    service_types: list[str] = Field(default_factory=list)
    spend: Decimal = Decimal(0)
    spend_share: float = 0.0
    hard_to_substitute: bool = False
    critical_services_without_exit_plan: int = 0
    subcontractor_appearances: int = 0


class GroupExposure(BaseModel):
    group_code: str
    group_name: str
    hq_country: str | None = None
    providers: list[str] = Field(default_factory=list)
    contracts: int = 0
    critical_functions: int = 0
    spend: Decimal = Decimal(0)
    spend_share: float = 0.0
    indirect_contracts: int = 0


class FunctionDependency(BaseModel):
    function_id: str
    entity_lei: str
    entity_name: str
    function_name: str
    providers: list[str] = Field(default_factory=list)
    provider_groups: list[str] = Field(default_factory=list)
    single_provider: bool = False
    hard_to_substitute: bool = False
    exit_plan_coverage: float = 1.0
    max_chain_rank: int = 0
    data_regions: list[str] = Field(default_factory=list)


class Share(BaseModel):
    key: str
    label: str
    count: int = 0
    spend: Decimal = Decimal(0)
    share: float = 0.0


class SubcontractorExposure(BaseModel):
    code: str
    name: str
    group_name: str
    chains: int = 0
    critical_chains: int = 0
    also_direct_provider: bool = False


class ExpiringContract(BaseModel):
    contract_ref: str
    provider: str
    end_date: date
    days_left: int
    functions: list[str] = Field(default_factory=list)


class ConcentrationAnalysis(BaseModel):
    reference_date: date
    reporting_currency: str | None
    entity_name: str | None
    totals: dict[str, int | float | str] = Field(default_factory=dict)
    total_spend: Decimal = Decimal(0)
    excluded_spend: dict[str, Decimal] = Field(default_factory=dict)
    hhi: float = 0.0
    hhi_band: str = "n/a"
    top1_share: float = 0.0
    top3_share: float = 0.0
    providers: list[ProviderExposure] = Field(default_factory=list)
    groups: list[GroupExposure] = Field(default_factory=list)
    critical_functions: list[FunctionDependency] = Field(default_factory=list)
    multi_cif_groups: list[GroupExposure] = Field(default_factory=list)
    hq_regions: list[Share] = Field(default_factory=list)
    group_regions: list[Share] = Field(default_factory=list)
    hq_countries: list[Share] = Field(default_factory=list)
    service_countries: list[Share] = Field(default_factory=list)
    data_locations_critical: list[Share] = Field(default_factory=list)
    service_types: list[Share] = Field(default_factory=list)
    chain_depths: list[Share] = Field(default_factory=list)
    max_chain_rank: int = 0
    subcontractors: list[SubcontractorExposure] = Field(default_factory=list)
    substitutability_critical: list[Share] = Field(default_factory=list)
    expiring_critical: list[ExpiringContract] = Field(default_factory=list)
    key_findings: list[KeyFinding] = Field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def _share(part: Decimal | int, whole: Decimal | int) -> float:
    return float(part) / float(whole) if whole else 0.0


def hhi(shares: list[float]) -> float:
    """Herfindahl-Hirschman index (0-10 000) of fractional shares."""
    return round(sum((s * 100) ** 2 for s in shares), 1)


def _band(value: float, cfg: AnalyticsConfig) -> str:
    if value >= cfg.hhi_high:
        return "highly concentrated"
    if value >= cfg.hhi_moderate:
        return "moderately concentrated"
    return "unconcentrated"


def _shares(counter: dict[str, int], spend: dict[str, Decimal] | None, labels: dict[str, str],
            by_spend: bool) -> list[Share]:
    total_count = sum(counter.values())
    total_spend = sum((spend or {}).values(), Decimal(0))
    keys = set(counter) | set(spend or {})
    out = [
        Share(key=k, label=labels.get(k, k), count=counter.get(k, 0),
              spend=(spend or {}).get(k, Decimal(0)),
              share=_share((spend or {}).get(k, Decimal(0)), total_spend) if by_spend
              else _share(counter.get(k, 0), total_count))
        for k in keys
    ]
    return sorted(out, key=lambda s: (-s.share, -s.count, s.label))


class _Index:
    """Pre-computed look-ups used by the analysis."""

    def __init__(self, reg: RegisterOfInformation) -> None:
        self.reg = reg
        self.providers = reg.providers_by_code()
        self.entities = reg.entities_by_lei()
        self.functions = reg.function_lookup()
        self.contracts = reg.contracts_by_ref()
        self.assessments: dict[tuple[object, ...], ServiceAssessment] = reg.assessments_by_key()
        self.critical_keys = reg.critical_function_keys()
        self.critical_ids = {fid for fid, _ in self.critical_keys}

    def provider_name(self, code: str) -> str:
        p = self.providers.get(code)
        return (p.legal_name or code) if p else code

    def group_of(self, code: str) -> str:
        p = self.providers.get(code)
        return (p.ultimate_parent_code or code) if p else code

    def is_critical(self, s: ContractSpecific) -> bool:
        key = (s.function_id or "", s.entity_lei or "")
        if key in self.functions:
            return key in self.critical_keys
        return (s.function_id or "") in self.critical_ids

    def assessment(self, s: ContractSpecific) -> ServiceAssessment | None:
        return self.assessments.get((s.contract_ref, s.provider_code, s.service_type))


# --------------------------------------------------------------------------- analysis


def analyse(register: RegisterOfInformation,
            config: AnalyticsConfig | None = None) -> ConcentrationAnalysis:
    """Compute concentration-risk metrics for ``register``."""
    cfg = config or AnalyticsConfig()
    idx = _Index(register)
    ref = cfg.reference_date or register.reference_date or date.today()
    currency = register.reporting_currency
    services = [s for s in register.b_02_02 if s.provider_code]

    # ---- spend attribution per provider
    direct: dict[str, set[str]] = defaultdict(set)  # contract -> providers
    for s in services:
        if s.contract_ref:
            direct[s.contract_ref].add(s.provider_code or "")
    spend_by_provider: dict[str, Decimal] = defaultdict(Decimal)
    excluded: dict[str, Decimal] = defaultdict(Decimal)
    for ref_no, contract_providers in direct.items():
        c = idx.contracts.get(ref_no)
        if c is None or c.annual_cost is None:
            continue
        if currency is not None and c.currency not in (None, currency):
            excluded[c.currency or "?"] += c.annual_cost
            continue
        portion = c.annual_cost / len(contract_providers)
        for pcode in contract_providers:
            spend_by_provider[pcode] += portion
    total_spend = sum(spend_by_provider.values(), Decimal(0))

    # ---- per-provider exposure
    exposures: dict[str, ProviderExposure] = {}

    def exposure(code: str) -> ProviderExposure:
        if code not in exposures:
            p: IctThirdPartyProvider | None = idx.providers.get(code)
            group = idx.group_of(code)
            exposures[code] = ProviderExposure(
                code=code, name=idx.provider_name(code),
                hq_country=p.hq_country if p else None,
                region=region_of(p.hq_country if p else None),
                group_code=group, group_name=idx.provider_name(group))
        return exposures[code]

    contracts_of: dict[str, set[str]] = defaultdict(set)
    entities_of: dict[str, set[str]] = defaultdict(set)
    functions_of: dict[str, set[tuple[str, str]]] = defaultdict(set)
    critical_of: dict[str, set[tuple[str, str]]] = defaultdict(set)
    types_of: dict[str, set[str]] = defaultdict(set)
    for s in services:
        code = s.provider_code or ""
        e = exposure(code)
        if s.contract_ref:
            contracts_of[code].add(s.contract_ref)
        if s.entity_lei:
            entities_of[code].add(s.entity_lei)
        fkey = (s.function_id or "", s.entity_lei or "")
        functions_of[code].add(fkey)
        if s.service_type:
            types_of[code].add(s.service_type.value)
        a = idx.assessment(s)
        if a and a.substitutability and a.substitutability.is_hard:
            e.hard_to_substitute = True
        if idx.is_critical(s):
            critical_of[code].add(fkey)
            if a is None or a.exit_plan is not True:
                e.critical_services_without_exit_plan += 1

    sub_chains: dict[str, set[str]] = defaultdict(set)
    sub_critical: dict[str, set[str]] = defaultdict(set)
    critical_contracts = {s.contract_ref for s in services if idx.is_critical(s)}
    for entry in register.b_05_02:
        if entry.provider_code and entry.rank and entry.rank > 1 and entry.contract_ref:
            sub_chains[entry.provider_code].add(entry.contract_ref)
            if entry.contract_ref in critical_contracts:
                sub_critical[entry.provider_code].add(entry.contract_ref)

    for code, e in exposures.items():
        e.contracts = len(contracts_of[code])
        e.entities = len(entities_of[code])
        e.functions = len(functions_of[code])
        e.critical_functions = len(critical_of[code])
        e.service_types = sorted(types_of[code])
        e.spend = spend_by_provider.get(code, Decimal(0))
        e.spend_share = _share(e.spend, total_spend)
        e.subcontractor_appearances = len(sub_chains.get(code, set()))
    providers = sorted(exposures.values(), key=lambda e: (-e.spend, -e.contracts, e.name))

    # ---- provider groups (ultimate parent)
    groups: dict[str, GroupExposure] = {}
    group_contracts: dict[str, set[str]] = defaultdict(set)
    group_critical: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for e in providers:
        g = groups.setdefault(e.group_code, GroupExposure(
            group_code=e.group_code, group_name=e.group_name,
            hq_country=(idx.providers[e.group_code].hq_country
                        if e.group_code in idx.providers else e.hq_country)))
        g.providers.append(e.name)
        g.spend += e.spend
        group_contracts[e.group_code] |= contracts_of[e.code]
        group_critical[e.group_code] |= critical_of[e.code]
    for code, chains in sub_chains.items():
        gcode = idx.group_of(code)
        if gcode in groups:
            groups[gcode].indirect_contracts += len(chains - group_contracts[gcode])
    for gcode, g in groups.items():
        g.contracts = len(group_contracts[gcode])
        g.critical_functions = len(group_critical[gcode])
        g.spend_share = _share(g.spend, total_spend)
    group_list = sorted(groups.values(), key=lambda g: (-g.spend, -g.contracts, g.group_name))
    shares = [g.spend_share for g in group_list]
    hhi_value = hhi(shares)

    # ---- critical function dependencies
    chain_rank: dict[str, int] = defaultdict(int)
    for entry in register.b_05_02:
        if entry.contract_ref and entry.rank:
            chain_rank[entry.contract_ref] = max(chain_rank[entry.contract_ref], entry.rank)
    fdeps: list[FunctionDependency] = []
    for (fid, lei) in sorted(idx.critical_keys):
        fn = idx.functions[(fid, lei)]
        svc = [s for s in services if (s.function_id, s.entity_lei) == (fid, lei)]
        provs = sorted({s.provider_code or "" for s in svc})
        assessments = [idx.assessment(s) for s in svc]
        with_exit = sum(1 for a in assessments if a is not None and a.exit_plan is True)
        regions = sorted({region_of(s.data_location_storage) for s in svc
                          if s.data_storage and s.data_location_storage})
        fdeps.append(FunctionDependency(
            function_id=fid, entity_lei=lei,
            entity_name=(idx.entities[lei].name or lei) if lei in idx.entities else lei,
            function_name=fn.function_name or fid,
            providers=[idx.provider_name(p) for p in provs],
            provider_groups=sorted({idx.provider_name(idx.group_of(p)) for p in provs}),
            single_provider=len({idx.group_of(p) for p in provs}) == 1,
            hard_to_substitute=any(a is not None and a.substitutability is not None
                                   and a.substitutability.is_hard for a in assessments),
            exit_plan_coverage=_share(with_exit, len(svc)) if svc else 0.0,
            max_chain_rank=max((chain_rank.get(s.contract_ref or "", 0) for s in svc), default=0),
            data_regions=regions,
        ))
    multi_cif = [g for g in group_list if g.critical_functions >= cfg.multi_cif_threshold]
    multi_cif.sort(key=lambda g: (-g.critical_functions, -g.spend))

    # ---- geography
    region_count: Counter[str] = Counter()
    region_spend: dict[str, Decimal] = defaultdict(Decimal)
    country_count: Counter[str] = Counter()
    country_spend: dict[str, Decimal] = defaultdict(Decimal)
    for e in providers:
        region_count[e.region] += 1
        region_spend[e.region] += e.spend
        key = e.hq_country or "Unknown"
        country_count[key] += 1
        country_spend[key] += e.spend
    group_region_count: Counter[str] = Counter()
    group_region_spend: dict[str, Decimal] = defaultdict(Decimal)
    for g in group_list:
        reg_key = region_of(g.hq_country)
        group_region_count[reg_key] += 1
        group_region_spend[reg_key] += g.spend
    service_country = Counter(s.service_country for s in services if s.service_country)
    data_loc = Counter(s.data_location_storage for s in services
                       if s.data_storage and s.data_location_storage and idx.is_critical(s))
    country_labels = {c: country_name(c) for c in
                      set(country_count) | set(service_country) | set(data_loc)}
    country_labels["Unknown"] = "Unknown"

    # ---- service types
    type_count = Counter(s.service_type.value for s in services if s.service_type)
    type_spend: dict[str, Decimal] = defaultdict(Decimal)
    rows_per_contract = Counter(s.contract_ref for s in services if s.service_type)
    for s in services:
        if not (s.service_type and s.contract_ref):
            continue
        c = idx.contracts.get(s.contract_ref)
        if c and c.annual_cost is not None and (currency is None or c.currency == currency):
            type_spend[s.service_type.value] += c.annual_cost / rows_per_contract[s.contract_ref]
    type_labels = {m.value: f"{m.value} {m.label}" for m in IctServiceType}

    # ---- subcontracting
    depth_count: Counter[str] = Counter()
    for contract in direct:
        depth_count[str(chain_rank.get(contract, 0))] += 1
    depth_labels = {"0": "Not reported", "1": "Direct only (rank 1)"}
    depth_labels.update({str(i): f"Rank {i}" for i in range(2, 20)})
    chain_depths = sorted(
        (Share(key=k, label=depth_labels.get(k, f"Rank {k}"), count=n,
               share=_share(n, sum(depth_count.values())))
         for k, n in depth_count.items()), key=lambda s: int(s.key))
    direct_codes = {s.provider_code for s in services}
    subs = sorted(
        (SubcontractorExposure(code=code, name=idx.provider_name(code),
                               group_name=idx.provider_name(idx.group_of(code)),
                               chains=len(chains), critical_chains=len(sub_critical.get(code, ())),
                               also_direct_provider=code in direct_codes)
         for code, chains in sub_chains.items()),
        key=lambda x: (-x.chains, -x.critical_chains, x.name))

    # ---- substitutability for critical services
    subst: Counter[str] = Counter()
    for s in services:
        if idx.is_critical(s):
            a = idx.assessment(s)
            subst[a.substitutability.value if a and a.substitutability else "NOT_ASSESSED"] += 1
    subst_labels: dict[str, str] = {m.value: m.label for m in Substitutability}
    subst_labels["NOT_ASSESSED"] = "No assessment"
    subst_order = [m.value for m in Substitutability] + ["NOT_ASSESSED"]
    subst_total = sum(subst.values())
    substitutability = [Share(key=k, label=subst_labels[k], count=subst[k],
                              share=_share(subst[k], subst_total))
                        for k in subst_order if subst.get(k)]

    # ---- expiring critical arrangements
    horizon = ref + timedelta(days=cfg.expiry_horizon_days)
    expiring: dict[str, ExpiringContract] = {}
    for s in services:
        if not (s.contract_ref and s.end_date and idx.is_critical(s)):
            continue
        if s.end_date == INDEFINITE_END_DATE or not (ref < s.end_date <= horizon):
            continue
        item = expiring.setdefault(s.contract_ref, ExpiringContract(
            contract_ref=s.contract_ref, provider=idx.provider_name(s.provider_code or ""),
            end_date=s.end_date, days_left=(s.end_date - ref).days))
        label = s.function_id or ""
        if label not in item.functions:
            item.functions.append(label)
    expiring_list = sorted(expiring.values(), key=lambda x: x.days_left)

    critical_services = [s for s in services if idx.is_critical(s)]
    with_exit = sum(1 for s in critical_services
                    if (a := idx.assessment(s)) is not None and a.exit_plan is True)
    cloud = sum(n for k, n in type_count.items() if k in ("S17", "S18", "S19"))
    m = register.maintainer
    analysis = ConcentrationAnalysis(
        reference_date=ref,
        reporting_currency=currency,
        entity_name=m.name if m else None,
        totals={
            "entities": len(register.b_01_02),
            "providers": len(register.b_05_01),
            "direct_providers": len(direct_codes),
            "provider_groups": len(group_list),
            "contracts": len(register.b_02_01),
            "services": len(services),
            "functions": len(register.b_06_01),
            "critical_functions": len(idx.critical_keys),
            "critical_services": len(critical_services),
            "critical_services_with_exit_plan": with_exit,
            "exit_plan_coverage": _share(with_exit, len(critical_services)),
            "cloud_service_share": _share(cloud, sum(type_count.values())),
            "subcontractors": len(sub_chains),
        },
        total_spend=total_spend,
        excluded_spend=dict(excluded),
        hhi=hhi_value,
        hhi_band=_band(hhi_value, cfg) if group_list else "n/a",
        top1_share=sum(shares[:1]),
        top3_share=sum(shares[:3]),
        providers=providers,
        groups=group_list,
        critical_functions=fdeps,
        multi_cif_groups=multi_cif,
        hq_regions=_shares(dict(region_count), dict(region_spend), {}, by_spend=True),
        group_regions=_shares(dict(group_region_count), dict(group_region_spend), {},
                              by_spend=True),
        hq_countries=_shares(dict(country_count), dict(country_spend), country_labels,
                             by_spend=True),
        service_countries=_shares(dict(service_country), None, country_labels, by_spend=False),
        data_locations_critical=_shares(dict(data_loc), None, country_labels, by_spend=False),
        service_types=_shares(dict(type_count), dict(type_spend), type_labels, by_spend=False),
        chain_depths=chain_depths,
        max_chain_rank=max(chain_rank.values(), default=0),
        subcontractors=subs,
        substitutability_critical=substitutability,
        expiring_critical=expiring_list,
    )
    analysis.key_findings = key_findings(analysis, cfg)
    return analysis


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def key_findings(a: ConcentrationAnalysis, cfg: AnalyticsConfig) -> list[KeyFinding]:
    """Derive plain-language key messages for a CRO from the metrics."""
    out: list[KeyFinding] = []
    if a.groups:
        top = a.groups[0]
        if top.spend_share >= cfg.single_group_share_threshold:
            out.append(KeyFinding(
                level=Level.HIGH, title=f"{top.group_name} accounts for {_pct(top.spend_share)} of "
                "ICT third-party spend",
                detail=f"Spend is {a.hhi_band} (HHI {a.hhi:,.0f}); the top three provider groups "
                f"account for {_pct(a.top3_share)}."))
        elif a.hhi >= cfg.hhi_moderate:
            out.append(KeyFinding(
                level=Level.MEDIUM, title=f"ICT spend is {a.hhi_band} (HHI {a.hhi:,.0f})",
                detail=f"Top three provider groups account for {_pct(a.top3_share)} of spend."))
    if a.multi_cif_groups:
        names = ", ".join(f"{g.group_name} ({g.critical_functions})"
                          for g in a.multi_cif_groups[:3])
        out.append(KeyFinding(
            level=Level.HIGH,
            title=f"{len(a.multi_cif_groups)} provider group(s) support "
            f"{cfg.multi_cif_threshold} or more critical or important functions",
            detail=f"Most exposed: {names}. A failure at one of these providers would affect "
            "several critical functions simultaneously."))
    single = [f for f in a.critical_functions if f.single_provider]
    hard_single = [f for f in single if f.hard_to_substitute]
    if single:
        out.append(KeyFinding(
            level=Level.HIGH if hard_single else Level.MEDIUM,
            title=f"{len(single)} of {len(a.critical_functions)} critical functions rely on a "
            "single provider group",
            detail=(f"{len(hard_single)} of them are also assessed as not or hardly substitutable."
                    if hard_single else "None is assessed as hard to substitute.")))
    total_cs = int(a.totals.get("critical_services", 0))
    coverage = float(a.totals.get("exit_plan_coverage", 0.0))
    if total_cs and coverage < 1:
        missing = total_cs - int(a.totals.get("critical_services_with_exit_plan", 0))
        out.append(KeyFinding(
            level=Level.HIGH if coverage < 0.9 else Level.MEDIUM,
            title=f"Exit plans cover {_pct(coverage)} of ICT services supporting critical "
            "functions",
            detail=f"{missing} service(s) lack a documented exit plan or assessment (DORA "
            "Art. 28(8))."))
    third = next((r for r in a.group_regions if r.key == "Third country"), None)
    if third and third.share >= 0.2:
        direct = next((r for r in a.hq_regions if r.key == "Third country"), None)
        direct_share = direct.share if direct else 0.0
        out.append(KeyFinding(
            level=Level.MEDIUM,
            title=f"{_pct(third.share)} of spend goes to provider groups headquartered outside "
            "the EEA and Switzerland",
            detail=f"{_pct(direct_share)} is contracted directly with third-country entities; "
            "the rest via EU/EEA subsidiaries of third-country groups. Consider third-country "
            "legal, data-transfer and supervisory-access risks."))
    if a.max_chain_rank >= cfg.deep_chain_rank:
        deep = sum(s.count for s in a.chain_depths if int(s.key) >= cfg.deep_chain_rank)
        out.append(KeyFinding(
            level=Level.MEDIUM,
            title=f"Subcontracting chains reach rank {a.max_chain_rank}",
            detail=f"{deep} arrangement(s) have chains of rank {cfg.deep_chain_rank} or deeper; "
            "visibility on fourth parties should be confirmed."))
    hidden = [s for s in a.subcontractors if s.critical_chains >= 2]
    if hidden:
        top_sub = hidden[0]
        out.append(KeyFinding(
            level=Level.MEDIUM,
            title=f"Hidden concentration: {top_sub.name} sits in {top_sub.chains} supply chains",
            detail=f"{len(hidden)} subcontractor(s) appear in two or more chains supporting "
            "critical functions; their failure would propagate through several direct "
            "providers."))
    if a.expiring_critical:
        soon = a.expiring_critical[0]
        out.append(KeyFinding(
            level=Level.MEDIUM if soon.days_left > 90 else Level.HIGH,
            title=f"{len(a.expiring_critical)} arrangement(s) supporting critical functions "
            f"expire within {cfg.expiry_horizon_days} days",
            detail=f"Earliest: {soon.contract_ref} with {soon.provider} on {soon.end_date} "
            f"({soon.days_left} days)."))
    if not out:
        out.append(KeyFinding(level=Level.LOW, title="No material concentration detected",
                              detail="None of the configured thresholds was exceeded."))
    order = {Level.HIGH: 0, Level.MEDIUM: 1, Level.LOW: 2}
    return sorted(out, key=lambda k: order[k.level])
