from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from dora_roi.io.parse import parse_raw, parse_row
from dora_roi.io.raw import RawRegister, RawRow, RawTable
from dora_roi.lei import make_lei
from dora_roi.model import (
    ContractGeneral,
    ContractSpecific,
    ContractType,
    Criticality,
    EntityInScope,
    Function,
    HierarchyInGroup,
    IctServiceType,
    IctThirdPartyProvider,
    ProviderCodeType,
    RegisterOfInformation,
    Substitutability,
    SupplyChainEntry,
    TerminationReason,
)
from dora_roi.model.codelists import AdditionalCodeType
from dora_roi.reporting import render, render_html, render_json, render_markdown, render_text
from dora_roi.validation import (
    RULES,
    Severity,
    ValidationConfig,
    engine_rules,
    rules_catalogue,
    validate,
)
from dora_roi.validation.references import REFERENCES

from conftest import ENTITY, PARENT, PROVIDER, SUBCONTRACTOR, build_valid_register

Mutation = Callable[[RegisterOfInformation], None]


def run(reg: RegisterOfInformation, **cfg: object) -> set[str]:
    report = validate(reg, config=ValidationConfig(**cfg))  # type: ignore[arg-type]
    assert not report.rule_failures, report.rule_failures
    return {f.rule_id for f in report.findings}


def test_valid_register_is_clean(valid_register: RegisterOfInformation) -> None:
    report = validate(valid_register)
    assert report.passed
    assert report.severity_counts() == {"error": 0, "warning": 0, "info": 0}, [
        (f.rule_id, f.message) for f in report.findings
    ]
    assert report.reference_date == date(2025, 12, 31)
    assert report.maintainer_lei == ENTITY


def _set(attr_path: str, value: object) -> Mutation:
    table, idx, attr = attr_path.split(".")

    def mutate(reg: RegisterOfInformation) -> None:
        setattr(getattr(reg, table)[int(idx)], attr, value)

    return mutate


def _many(*mutations: Mutation) -> Mutation:
    def mutate(reg: RegisterOfInformation) -> None:
        for m in mutations:
            m(reg)

    return mutate


def _add(record_factory: Callable[[], object]) -> Mutation:
    def mutate(reg: RegisterOfInformation) -> None:
        reg.add(record_factory())  # type: ignore[arg-type]

    return mutate


def _clear(table: str) -> Mutation:
    def mutate(reg: RegisterOfInformation) -> None:
        getattr(reg, table).clear()

    return mutate


OTHER_LEI = make_lei("OTHERPROVIDER00001")

CASES: list[tuple[str, Mutation]] = [
    ("FLD-001", _set("b_02_02.0.governing_law_country", None)),
    ("FLD-010", _add(lambda: ContractGeneral(contract_ref="C-001"))),
    ("FLD-011", _clear("b_01_01")),
    ("FLD-012", _clear("b_06_01")),
    ("FLD-013", _set("b_05_01.1.provider_code_type", ProviderCodeType.EUID)),
    ("FLD-013", _many(_set("b_05_01.1.provider_code", "SUB"),
                      _set("b_05_01.1.ultimate_parent_code", "SUB"))),
    ("XRF-001", _set("b_07_01.0.contract_ref", "C-404")),
    ("XRF-002", _set("b_06_01.0.entity_lei", PARENT)),
    ("XRF-003", _set("b_02_02.0.provider_code", OTHER_LEI)),
    ("XRF-004", _set("b_02_02.0.function_id", "F-X")),
    ("XRF-005", _many(_set("b_06_01.0.entity_lei", PARENT),
                      _add(lambda: EntityInScope(lei=PARENT)))),
    ("XRF-006", _add(lambda: ContractGeneral(contract_ref="C-002"))),
    ("XRF-007", _clear("b_03_01")),
    ("XRF-008", _clear("b_03_02")),
    ("XRF-009", _clear("b_04_01")),
    ("XRF-010", _add(lambda: IctThirdPartyProvider(provider_code=OTHER_LEI))),
    ("XRF-011", _many(_set("b_02_01.0.contract_type", ContractType.SUBSEQUENT),
                      _set("b_02_01.0.overarching_ref", "C-999"))),
    ("XRF-011", _many(_add(lambda: ContractGeneral(contract_ref="C-002",
                                                   contract_type=ContractType.STANDALONE)),
                      _set("b_02_01.0.contract_type", ContractType.SUBSEQUENT),
                      _set("b_02_01.0.overarching_ref", "C-002"))),
    ("XRF-011", _many(_set("b_02_01.0.contract_type", ContractType.SUBSEQUENT),
                      _set("b_02_01.0.overarching_ref", "C-001"))),
    ("XRF-012", _many(_set("b_04_01.0.is_branch", True), _set("b_04_01.0.branch_code", "BR1"))),
    ("XRF-013", _set("b_07_01.0.service_type", IctServiceType.S18)),
    ("XRF-014", _many(_set("b_01_02.0.hierarchy", HierarchyInGroup.SUBSIDIARY),
                      _set("b_01_02.0.parent_lei", PARENT))),
    ("XRF-015", _add(lambda: EntityInScope(lei=PARENT))),
    ("SC-001", _set("b_05_02.0.provider_code", SUBCONTRACTOR)),
    ("SC-002", _set("b_05_02.1.recipient_code", None)),
    ("SC-002", _set("b_05_02.1.recipient_code_type", None)),
    ("SC-003", _set("b_05_02.1.rank", 3)),
    ("SC-004", _set("b_05_02.0.recipient_code", PROVIDER)),
    ("SC-005", _add(lambda: SupplyChainEntry(
        contract_ref="C-001", service_type=IctServiceType.S19, provider_code=PROVIDER,
        provider_code_type=ProviderCodeType.LEI, rank=3, recipient_code=SUBCONTRACTOR,
        recipient_code_type=ProviderCodeType.LEI))),
    ("SC-006", _clear("b_05_02")),
    ("BUS-001", _set("b_02_02.0.end_date", date(2022, 1, 1))),
    ("BUS-002", _set("b_02_02.0.end_date", date(2025, 6, 30))),
    ("BUS-003", _set("b_02_02.0.termination_reason", TerminationReason.EXPIRED)),
    ("BUS-004", _set("b_02_02.0.data_location_storage", None)),
    ("BUS-005", _set("b_02_02.0.data_sensitivity", None)),
    ("BUS-006", _set("b_02_02.0.data_location_processing", None)),
    ("BUS-007", _set("b_02_01.0.overarching_ref", "C-001")),
    ("BUS-007", _set("b_02_01.0.contract_type", ContractType.SUBSEQUENT)),
    ("BUS-008", _set("b_02_01.0.currency", "USD")),
    ("BUS-009", _set("b_05_01.0.total_annual_cost", Decimal("50000"))),
    ("BUS-010", _set("b_01_02.0.hierarchy", HierarchyInGroup.SUBSIDIARY)),
    ("BUS-010", _set("b_01_02.0.parent_lei", PARENT)),
    ("BUS-010", _many(_set("b_01_02.0.hierarchy", HierarchyInGroup.SUBSIDIARY),
                      _set("b_01_02.0.parent_lei", ENTITY))),
    ("BUS-011", _set("b_01_02.0.deletion_date", date(2024, 1, 1))),
    ("BUS-012", _set("b_06_01.0.last_assessment_date", date(2026, 3, 1))),
    ("BUS-013", _set("b_04_01.0.is_branch", True)),
    ("BUS-013", _set("b_04_01.0.branch_code", "BR1")),
    ("BUS-014", _set("b_05_01.0.additional_code", "HRB 1234")),
    ("BUS-014", _set("b_05_01.0.additional_code_type", AdditionalCodeType.VAT)),
    ("BUS-015", _set("b_06_01.0.rto_hours", None)),
    ("BUS-016", _set("b_06_01.0.criticality", Criticality.NOT_ASSESSED)),
    ("BUS-017", _set("b_06_01.0.last_assessment_date", date(2024, 1, 1))),
    ("BUS-018", _clear("b_07_01")),
    ("BUS-019", _set("b_07_01.0.exit_plan", False)),
    ("BUS-020", _set("b_07_01.0.substitutability", Substitutability.NOT_SUBSTITUTABLE)),
    ("BUS-021", _set("b_07_01.0.alternative_providers", None)),
    ("BUS-022", _set("b_07_01.0.last_audit_date", None)),
    ("BUS-022", _set("b_07_01.0.last_audit_date", date(2020, 1, 1))),
    ("BUS-023", _set("b_02_02.0.provider_code", ENTITY)),
    ("BUS-024", _set("b_02_02.0.end_date", date(2090, 1, 1))),
    ("BUS-025", _set("b_05_01.1.legal_name", "SAAS VENDOR Ltd.")),
]


@pytest.mark.parametrize(("rule_id", "mutation"), CASES,
                         ids=[f"{r}-{i}" for i, (r, _) in enumerate(CASES)])
def test_rule_fires(rule_id: str, mutation: Mutation) -> None:
    reg = build_valid_register()
    mutation(reg)
    assert rule_id in run(reg)


def test_every_engine_rule_has_a_test_case() -> None:
    tested = {rule_id for rule_id, _ in CASES}
    missing = {r.id for r in engine_rules()} - tested
    assert not missing, f"rules without a firing test: {sorted(missing)}"


def test_catalogue_metadata_is_complete() -> None:
    cat = rules_catalogue()
    assert len(cat) == len(RULES) >= 60
    for r in cat:
        assert r.title and r.description and r.references, r.id
        for ref in r.references:
            assert ref in REFERENCES, f"{r.id}: unknown reference {ref!r}"


def test_disable_and_override(valid_register: RegisterOfInformation) -> None:
    valid_register.b_07_01[0].exit_plan = False
    assert "BUS-019" not in run(valid_register, disabled_rules=frozenset({"BUS-019"}))
    report = validate(valid_register, config=ValidationConfig(
        severity_overrides={"BUS-019": Severity.WARNING}))
    f = next(f for f in report.findings if f.rule_id == "BUS-019")
    assert f.severity is Severity.WARNING and report.passed


def test_finding_location_and_key(valid_register: RegisterOfInformation) -> None:
    valid_register.b_02_02[0].set_provenance(7, "book.xlsx")
    valid_register.b_02_02[0].governing_law_country = None
    report = validate(valid_register)
    f = next(f for f in report.findings if f.rule_id == "FLD-001")
    assert (f.template, f.row, f.column, f.source) == ("B_02.02", 7, "c0120", "book.xlsx")
    assert f.location == "B_02.02 / row 7 / c0120"
    assert f.record_key and f.record_key.startswith("C-001 | ")


def test_parse_findings_do_not_double_report() -> None:
    record, findings = parse_row(ContractSpecific, RawRow(5, {
        "c0010": "C-1", "c0120": "UK", "c0070": "31/12/2024", "c0060": "S20", "c0100": "-3",
        "c0140": "perhaps", "c0020": ENTITY.lower(),
    }), "x.csv")
    rules = {f.rule_id for f in findings}
    assert rules == {"FLD-005", "FLD-003", "FLD-004", "FLD-007", "FLD-008"}
    assert record.invalid_fields == {"governing_law_country", "start_date", "service_type",
                                     "notice_period_entity", "data_storage"}
    assert record.entity_lei == ENTITY and record.row == 5
    assert all(f.record_key and f.record_key.startswith("C-1") for f in findings)
    reg = RegisterOfInformation()
    reg.add(record)
    report = validate(reg, parse_findings=findings)
    mandatory = {f.column for f in report.findings if f.rule_id == "FLD-001"}
    assert "c0120" not in mandatory and "c0070" not in mandatory and "c0030" in mandatory


def test_parse_raw_and_text_length() -> None:
    raw = RawRegister(tables={"B_02.01": RawTable("B_02.01", ["c0010"], [
        RawRow(2, {"c0010": "x" * 300, "c0040": "EURO", "c0050": "abc"}),
    ], source="t.csv")})
    result = parse_raw(raw)
    assert {f.rule_id for f in result.findings} == {"FLD-009", "FLD-006", "FLD-007"}
    assert result.register.b_02_01[0].source == "t.csv"


def test_parse_disabled_and_overridden_findings() -> None:
    _, findings = parse_row(ContractGeneral, RawRow(2, {"c0040": "EURO"}))
    reg = RegisterOfInformation()
    report = validate(reg, parse_findings=findings,
                      config=ValidationConfig(disabled_rules=frozenset({"FLD-006"})))
    assert "FLD-006" not in {f.rule_id for f in report.findings}
    report = validate(reg, parse_findings=findings,
                      config=ValidationConfig(severity_overrides={"FLD-006": Severity.INFO}))
    assert next(f for f in report.findings if f.rule_id == "FLD-006").severity is Severity.INFO


def test_multi_provider_cost_not_attributed(valid_register: RegisterOfInformation) -> None:
    second = valid_register.b_02_02[0].model_copy(update={"provider_code": SUBCONTRACTOR})
    valid_register.add(second)
    valid_register.b_05_01[0].total_annual_cost = Decimal(1)
    assert "BUS-009" not in run(valid_register)


def test_function_other_entity_counts_as_critical(valid_register: RegisterOfInformation) -> None:
    valid_register.add(EntityInScope(lei=PARENT))
    valid_register.add(Function(function_id="F-PAY", entity_lei=PARENT,
                                criticality=Criticality.NOT_CRITICAL))
    valid_register.b_06_01[0].entity_lei = PARENT
    valid_register.b_06_01.pop(0)
    valid_register.add(Function(function_id="F-PAY", entity_lei=make_lei("THIRDENTITY0000001"),
                                criticality=Criticality.CRITICAL))
    # service's (function, entity) pair is unknown -> falls back to function id criticality
    assert "BUS-019" not in run(valid_register)


def test_report_renderers(valid_register: RegisterOfInformation) -> None:
    valid_register.b_07_01[0].exit_plan = False
    valid_register.b_02_02[0].data_location_processing = None
    report = validate(valid_register, source="demo.xlsx")
    data = json.loads(render_json(report))
    assert data["schema"] == "dora-roi-toolkit/validation-report/v1"
    assert data["passed"] is False
    assert data["summary"]["severity_counts"]["error"] == 1
    assert {f["rule_id"] for f in data["findings"]} == {"BUS-019", "BUS-006"}
    md = render_markdown(report)
    assert "BUS-019" in md and "❌ FAILED" in md and "| B_07.01 |" in md
    html = render_html(report)
    assert "<!doctype html>" in html and "Not ready for submission" in html
    assert "demo.xlsx" in html
    assert "FAILED" in render_text(report)
    assert render(report, "md") == md
    assert render(report, "json").startswith("{")
    assert render(report, "html").startswith("<!doctype html>")
    assert render(report, "text").startswith("FAILED")


def test_report_pass_states(valid_register: RegisterOfInformation) -> None:
    report = validate(valid_register)
    assert "Passed." in render_html(report)
    assert "✅ PASSED" in render_markdown(report)
    valid_register.b_02_02[0].data_location_processing = None
    report = validate(valid_register)
    assert report.passed and "Passed with warnings" in render_html(report)


def test_markdown_truncation_and_empty() -> None:
    reg = RegisterOfInformation()
    reg.b_02_02 = [ContractSpecific(contract_ref=f"C{i}") for i in range(30)]
    report = validate(reg)
    md = render_markdown(report, max_findings=5)
    assert "more findings omitted" in md
    text = render_text(report, max_findings=3)
    assert "more (use --format" in text


def test_report_helpers(valid_register: RegisterOfInformation) -> None:
    valid_register.b_06_01[0].criticality = Criticality.NOT_ASSESSED
    valid_register.add(EntityInScope(lei=PARENT, hierarchy=HierarchyInGroup.SUBSIDIARY,
                                     parent_lei=make_lei("OUTSIDESCOPE000001")))
    report = validate(valid_register)
    assert report.warnings and report.infos and report.errors
    assert sum(report.severity_counts().values()) == len(report.findings)
    assert report.by_rule()[0][0].severity is Severity.ERROR


def test_euid_provider_code_valid(valid_register: RegisterOfInformation) -> None:
    for rec in (valid_register.b_05_01[1],):
        rec.provider_code_type = ProviderCodeType.EUID
        rec.provider_code = "DEK1101R.HRB116737"
        rec.ultimate_parent_code = "DEK1101R.HRB116737"
        rec.ultimate_parent_code_type = ProviderCodeType.EUID
    for e in valid_register.b_05_02:
        if e.provider_code == SUBCONTRACTOR:
            e.provider_code = "DEK1101R.HRB116737"
            e.provider_code_type = ProviderCodeType.EUID
    assert "FLD-013" not in run(valid_register)
