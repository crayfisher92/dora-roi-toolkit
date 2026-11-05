from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dora_roi.model import (
    TEMPLATE_MODELS,
    TEMPLATES_BY_CODE,
    ContractSpecific,
    Criticality,
    EntityInScope,
    Function,
    IctServiceType,
    Kind,
    RegisterOfInformation,
    Requirement,
    Substitutability,
    serialise_value,
)
from dora_roi.model.codelists import ALL_CODELISTS, ContractType
from dora_roi.model.refdata import COUNTRIES, CURRENCIES, country_name, region_of

LEI = "529900T8BM49AURSDO55"


def test_all_templates_present() -> None:
    codes = [m.TEMPLATE for m in TEMPLATE_MODELS]
    assert codes == [
        "B_01.01", "B_01.02", "B_01.03", "B_02.01", "B_02.02", "B_02.03", "B_03.01",
        "B_03.02", "B_03.03", "B_04.01", "B_05.01", "B_05.02", "B_06.01", "B_07.01",
    ]
    assert set(TEMPLATES_BY_CODE) == set(codes)


@pytest.mark.parametrize("model", TEMPLATE_MODELS)
def test_columns_metadata_consistent(model: type) -> None:
    cols = model.columns()
    assert cols, model
    codes = [c.code for c in cols]
    assert codes == sorted(codes), "columns must be declared in ITS order"
    assert len(set(codes)) == len(codes)
    for key in model.KEY:
        assert key in model.model_fields
    for c in cols:
        if c.col.kind is Kind.CODELIST:
            assert c.col.codelist is not None
        if c.col.requirement is Requirement.CONDITIONAL:
            assert c.col.condition, f"{model.TEMPLATE} {c.code} needs a condition text"
    assert model.column(cols[0].attr) is cols[0]
    assert model.column_by_code(cols[0].code) is cols[0]
    assert model.column_by_code("c9999") is None
    with pytest.raises(KeyError):
        model.column("nope")


def test_refdata() -> None:
    assert len(COUNTRIES) == 249
    assert "EUR" in CURRENCIES and "HRK" not in CURRENCIES
    assert country_name("CH") == "Switzerland" and country_name(None) == "—"
    assert country_name("ZZ") == "ZZ"
    assert region_of("DE") == "EU"
    assert region_of("NO") == "EEA (non-EU)"
    assert region_of("CH") == "Switzerland"
    assert region_of("US") == "Third country"
    assert region_of(None) == "Unknown"


def test_codelist_lookup_by_code_label_alias_and_prefix() -> None:
    assert IctServiceType.lookup("s19") is IctServiceType.S19
    assert IctServiceType.lookup("Cloud services: SaaS") is IctServiceType.S19
    assert IctServiceType.lookup("SaaS") is IctServiceType.S19
    assert IctServiceType.lookup("eba_TA:S17") is IctServiceType.S17
    assert IctServiceType.lookup("S20") is None
    assert Criticality.lookup("Yes") is Criticality.CRITICAL
    assert ContractType.lookup("master") is ContractType.OVERARCHING
    assert IctServiceType.S17.is_cloud and not IctServiceType.S01.is_cloud
    assert Substitutability.HIGHLY_COMPLEX.is_hard
    for cl in ALL_CODELISTS:
        assert cl.describe()
        for m in cl:
            assert cl.lookup(m.label) is m


def test_contract_specific_parsing_coerces_types() -> None:
    row = ContractSpecific.model_validate(
        {
            "contract_ref": " C-1 ",
            "entity_lei": LEI.lower(),
            "function_id": 7,
            "service_type": "PaaS",
            "start_date": "2024-01-01 00:00:00",
            "end_date": "",
            "data_storage": "Yes",
            "notice_period_entity": 30.0,
        }
    )
    assert row.contract_ref == "C-1"
    assert row.entity_lei == LEI
    assert row.function_id == "7"
    assert row.service_type is IctServiceType.S18
    assert row.start_date == date(2024, 1, 1)
    assert row.end_date is None
    assert row.data_storage is True
    assert row.notice_period_entity == 30
    assert row.to_row()["c0060"] == "S18"
    assert row.key_str().startswith("C-1 | " + LEI)


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("entity_lei", "529900T8BM49AURSDO56", "roi_lei"),
        ("service_type", "S20", "roi_codelist"),
        ("start_date", "31/12/2024", "roi_date"),
        ("start_date", "2024-02-30", "roi_date"),
        ("governing_law_country", "UK", "roi_country"),
        ("data_storage", "maybe", "roi_bool"),
        ("notice_period_entity", -1, "greater_than_equal"),
    ],
)
def test_format_errors(field: str, value: object, error_type: str) -> None:
    with pytest.raises(ValidationError) as exc:
        ContractSpecific.model_validate({field: value})
    assert exc.value.errors()[0]["type"] == error_type


def test_entity_amount_and_currency() -> None:
    e = EntityInScope.model_validate(
        {"lei": LEI, "currency": "chf", "total_assets": "1,250,000.50"}
    )
    assert e.currency == "CHF"
    assert e.total_assets == Decimal("1250000.50")
    with pytest.raises(ValidationError):
        EntityInScope.model_validate({"currency": "EURO"})


def test_serialise_value() -> None:
    assert serialise_value(None) is None
    assert serialise_value(True) == "true"
    assert serialise_value(False) == "false"
    assert serialise_value(Decimal("10.500")) == "10.5"
    assert serialise_value(Decimal("100")) == "100"
    assert serialise_value(date(2025, 3, 31)) == "2025-03-31"
    assert serialise_value(IctServiceType.S01) == "S01"
    assert serialise_value(5) == "5"


def test_register_lookups() -> None:
    reg = RegisterOfInformation()
    assert reg.is_empty() and reg.maintainer is None and reg.reference_date is None
    assert reg.reporting_currency is None
    reg.add(EntityInScope(lei=LEI, currency="EUR"))
    f = Function(function_id="F1", entity_lei=LEI, criticality=Criticality.CRITICAL)
    reg.add(f)
    svc = ContractSpecific(contract_ref="C1", entity_lei=LEI, function_id="F1")
    reg.add(svc)
    assert reg.critical_function_keys() == {("F1", LEI)}
    assert reg.supports_critical(svc)
    other = ContractSpecific(contract_ref="C1", entity_lei="5493001KJTIIGC8Y1R12", function_id="F1")
    assert reg.supports_critical(other)
    assert not reg.supports_critical(ContractSpecific(function_id="F9"))
    assert reg.services_by_contract()["C1"] == [svc]
    assert reg.counts()["B_02.02"] == 1
    assert reg.summary()["counts"]["B_06.01"] == 1
    assert len(list(reg.iter_all())) == 3
    rec = reg.b_01_02[0]
    rec.set_provenance(4, "file.xlsx", frozenset({"name"}))
    assert rec.row == 4 and rec.source == "file.xlsx" and rec.invalid_fields == {"name"}
