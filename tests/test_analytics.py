from __future__ import annotations

from datetime import date
from decimal import Decimal

from dora_roi.analytics import AnalyticsConfig, Level, analyse, hhi
from dora_roi.analytics.concentration import _band
from dora_roi.lei import make_lei
from dora_roi.model import (
    ContractGeneral,
    ContractSpecific,
    ContractType,
    Criticality,
    Function,
    IctServiceType,
    IctThirdPartyProvider,
    ProviderCodeType,
    RegisterOfInformation,
    ServiceAssessment,
    Substitutability,
    SupplyChainEntry,
)
from dora_roi.reporting.charts import Bar, Segment, column_chart, hbar_chart, segmented_bar
from dora_roi.reporting.executive import money, pct, render_executive_summary
from dora_roi.validation import validate

from conftest import ENTITY, PROVIDER, SUBCONTRACTOR, build_valid_register

US_HYPER = make_lei("USHYPERSCALER00001")
IE_HYPER = make_lei("IEHYPERSCALER00001")


def _add_provider(reg: RegisterOfInformation, code: str, name: str, country: str,
                  parent: str | None = None) -> None:
    reg.add(IctThirdPartyProvider(provider_code=code, provider_code_type=ProviderCodeType.LEI,
                                  legal_name=name, hq_country=country, currency="EUR",
                                  total_annual_cost=Decimal(10**7),
                                  ultimate_parent_code=parent or code,
                                  ultimate_parent_code_type=ProviderCodeType.LEI))


def _add_contract(reg: RegisterOfInformation, ref: str, provider: str, cost: int,
                  function: str = "F-PAY", service: IctServiceType = IctServiceType.S17,
                  currency: str = "EUR", end: date = date(9999, 12, 31),
                  exit_plan: bool | None = True,
                  subst: Substitutability = Substitutability.HIGHLY_COMPLEX) -> None:
    reg.add(ContractGeneral(contract_ref=ref, contract_type=ContractType.STANDALONE,
                            currency=currency, annual_cost=Decimal(cost)))
    reg.add(ContractSpecific(contract_ref=ref, entity_lei=ENTITY, provider_code=provider,
                             provider_code_type=ProviderCodeType.LEI, function_id=function,
                             service_type=service, start_date=date(2022, 1, 1), end_date=end,
                             service_country="IE", data_storage=True,
                             data_location_storage="US"))
    if exit_plan is not None:
        reg.add(ServiceAssessment(contract_ref=ref, provider_code=provider,
                                  provider_code_type=ProviderCodeType.LEI, service_type=service,
                                  substitutability=subst, exit_plan=exit_plan))


def concentrated_register() -> RegisterOfInformation:
    reg = build_valid_register()
    _add_provider(reg, US_HYPER, "Nimbus Inc.", "US")
    _add_provider(reg, IE_HYPER, "Nimbus Ireland Ltd", "IE", parent=US_HYPER)
    for i, fid in enumerate(["F-PAY", "F-CORE", "F-AML"]):
        reg.add(Function(function_id=fid if fid != "F-PAY" else "F-PAY2", entity_lei=ENTITY,
                         criticality=Criticality.CRITICAL, function_name=fid))
        _add_contract(reg, f"H-{i}", IE_HYPER, 2_000_000, function=fid if fid != "F-PAY"
                      else "F-PAY2", exit_plan=(i != 0))
    _add_contract(reg, "H-US", US_HYPER, 500_000, function="F-CORE", end=date(2026, 3, 31))
    _add_contract(reg, "H-CHF", US_HYPER, 999, function="F-CORE", currency="CHF",
                  exit_plan=None)
    # Nimbus as subcontractor in two critical chains (rank 2) and a rank-3 chain
    for ref in ("C-001", "H-0"):
        direct = PROVIDER if ref == "C-001" else IE_HYPER
        if ref != "C-001":
            reg.add(SupplyChainEntry(contract_ref=ref, service_type=IctServiceType.S17,
                                     provider_code=direct, rank=1))
        reg.add(SupplyChainEntry(contract_ref=ref, service_type=IctServiceType.S19
                                 if ref == "C-001" else IctServiceType.S17,
                                 provider_code=US_HYPER, rank=2,
                                 recipient_code=direct))
    reg.add(SupplyChainEntry(contract_ref="C-001", service_type=IctServiceType.S19,
                             provider_code=US_HYPER, rank=3, recipient_code=SUBCONTRACTOR))
    return reg


def test_hhi_and_bands() -> None:
    assert hhi([1.0]) == 10000
    assert hhi([0.5, 0.5]) == 5000
    assert hhi([]) == 0
    cfg = AnalyticsConfig()
    assert _band(1000, cfg) == "unconcentrated"
    assert _band(2000, cfg) == "moderately concentrated"
    assert _band(3000, cfg) == "highly concentrated"


def test_simple_register() -> None:
    a = analyse(build_valid_register())
    assert a.total_spend == Decimal(100000)
    assert a.top1_share == 1.0 and a.hhi == 10000
    assert a.totals["critical_functions"] == 1 and a.totals["exit_plan_coverage"] == 1.0
    assert a.critical_functions[0].single_provider
    assert a.critical_functions[0].max_chain_rank == 2
    assert a.subcontractors[0].code == SUBCONTRACTOR
    assert a.chain_depths[0].key == "2"
    assert a.key_findings[0].level is Level.HIGH


def test_empty_register() -> None:
    a = analyse(RegisterOfInformation(), AnalyticsConfig(reference_date=date(2025, 1, 1)))
    assert a.hhi_band == "n/a" and a.total_spend == 0
    assert [k.level for k in a.key_findings] == [Level.LOW]
    html = render_executive_summary(RegisterOfInformation())
    assert "No material concentration" in html and "No data." in html


def test_concentrated_register() -> None:
    reg = concentrated_register()
    a = analyse(reg, AnalyticsConfig(multi_cif_threshold=3))
    group = a.groups[0]
    assert group.group_code == US_HYPER
    assert group.group_name == "Nimbus Inc."
    assert set(group.providers) == {"Nimbus Inc.", "Nimbus Ireland Ltd"}
    assert group.spend == Decimal(6_500_000)
    assert group.critical_functions == 3
    assert a.excluded_spend == {"CHF": Decimal(999)}
    assert a.multi_cif_groups and a.multi_cif_groups[0].group_code == US_HYPER
    nimbus_sub = next(s for s in a.subcontractors if s.code == US_HYPER)
    assert nimbus_sub.chains == 2 and nimbus_sub.also_direct_provider
    assert a.max_chain_rank == 3
    assert any(r.key == "Third country" for r in a.hq_regions)
    assert a.group_regions[0].key == "Third country"
    assert a.expiring_critical and a.expiring_critical[0].contract_ref == "H-US"
    assert a.data_locations_critical[0].key == "US"
    kinds = " ".join(k.title for k in a.key_findings)
    for fragment in ("accounts for", "support 3 or more", "Exit plans cover",
                     "outside the EEA", "rank 3", "Hidden concentration", "expire within"):
        assert fragment in kinds, fragment
    assert a.substitutability_critical[0].key == "MEDIUM" or a.substitutability_critical
    assert {s.key for s in a.substitutability_critical} >= {"HIGHLY_COMPLEX", "NOT_ASSESSED"}


def test_moderate_concentration_message() -> None:
    reg = build_valid_register()
    for i in range(5):
        code = make_lei(f"EVENPROVIDER{i:06d}")
        _add_provider(reg, code, f"Vendor {i}", "DE")
        _add_contract(reg, f"E-{i}", code, 100000, exit_plan=True)
    a = analyse(reg, AnalyticsConfig(single_group_share_threshold=0.5))
    assert any("HHI" in k.title for k in a.key_findings)


def test_split_cost_between_two_providers() -> None:
    reg = build_valid_register()
    second = reg.b_02_02[0].model_copy(update={"provider_code": SUBCONTRACTOR})
    reg.add(second)
    a = analyse(reg)
    spends = {p.code: p.spend for p in a.providers}
    assert spends[PROVIDER] == spends[SUBCONTRACTOR] == Decimal(50000)


def test_charts_render() -> None:
    svg = hbar_chart([Bar("A very long provider name exceeding the limit", 0.5, "50%"),
                      Bar("B", 0.0, "0%", muted=True)], title="T")
    assert svg.startswith("<svg") and "…" in svg and 'aria-label="T"' in svg
    assert "No data" in hbar_chart([], title="x")
    col = column_chart([Bar("Rank 1", 3, "3"), Bar("Rank 2", 0, "0")], title="C")
    assert col.count("<path") == 1
    assert "No data" in column_chart([], title="x")
    seg = segmented_bar([Segment("EU", 3, "75%", "--series-1"),
                         Segment("None", 0, "0%", "--series-2")], title="S")
    assert "flex:1.000000" in seg and "None" not in seg
    assert "No data" in segmented_bar([], title="x")


def test_money_pct() -> None:
    assert money(Decimal("12400000"), "EUR") == "EUR 12.4m"
    assert money(2_500_000_000) == "2.5bn"
    assert money(850_000, "CHF") == "CHF 850k"
    assert money(12) == "12"
    assert pct(0.256) == "26%"


def test_executive_summary_html() -> None:
    reg = concentrated_register()
    html = render_executive_summary(reg, validate(reg), client_name="Client X",
                                    prepared_by="GRC Team")
    assert "<!doctype html>" in html and "Client X" in html and "GRC Team" in html
    assert "Key messages" in html and "Nimbus Inc." in html
    assert "Register data quality" in html and 'id="viz-tip"' in html
    assert "Excluded (other currencies)" in html
    assert "expiring within" in html
