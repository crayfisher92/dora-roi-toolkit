"""rc.2: results that can be trusted – no row inflation, visible data gaps, no invented values.

Findings of the independent model review (November 2026, see CHANGELOG 0.2.0-rc.2).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from dora_roi.analytics import AnalyticsConfig, Level, analyse
from dora_roi.analytics.renewals import NoticeStatus, notice_schedule
from dora_roi.cli import main
from dora_roi.contracts import AssessmentBook, evaluate, remediation_plan
from dora_roi.incidents import IncidentLog
from dora_roi.incidents.report import overview
from dora_roi.io.excel import write_workbook
from dora_roi.io.xbrl_csv import ExportBlockedError, XbrlCsvOptions, build_package_files
from dora_roi.model import (
    ContractGeneral,
    Criticality,
    Function,
    IctServiceType,
    ProviderCodeType,
    ServiceAssessment,
    Substitutability,
)
from dora_roi.quality import quality_score
from dora_roi.readiness import Rag, build_readiness
from dora_roi.validation import validate
from dora_roi.web.app import create_app

from conftest import ENTITY, PROVIDER, REF_DATE, build_valid_register

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
CFG = AnalyticsConfig(reference_date=REF_DATE)


def second_service(reg, exit_plan: bool | None = False) -> None:  # type: ignore[no-untyped-def]
    """A second critical service (contract C-002, same provider) with its own assessment."""
    reg.add(ContractGeneral(contract_ref="C-002", contract_type=reg.b_02_01[0].contract_type,
                            currency="EUR", annual_cost=Decimal("50000")))
    row = reg.b_02_02[0].model_copy(update={"contract_ref": "C-002",
                                            "service_type": IctServiceType.S02})
    reg.add(row)
    reg.add(ServiceAssessment(
        contract_ref="C-002", provider_code=PROVIDER, provider_code_type=ProviderCodeType.LEI,
        service_type=IctServiceType.S02, substitutability=Substitutability.HIGHLY_COMPLEX,
        exit_plan=exit_plan))


def test_location_rows_do_not_inflate_service_counts() -> None:
    reg = build_valid_register()
    # the same service provided from three countries = three B_02.02 rows, one service
    for country in ("FR", "IT"):
        reg.add(reg.b_02_02[0].model_copy(update={"service_country": country}))
    second_service(reg, exit_plan=False)
    a = analyse(reg, CFG)
    assert a.totals["service_rows"] == 4 and a.totals["services"] == 2
    assert a.totals["critical_services"] == 2
    assert a.totals["exit_plan_coverage"] == pytest.approx(0.5)  # was 0.75 with row counting
    fn = a.critical_functions[0]
    assert fn.exit_plan_coverage == pytest.approx(0.5)
    assert sum(s.count for s in a.substitutability_critical) == 2
    assert {s.key: s.count for s in a.service_types} == {"S19": 1, "S02": 1}
    assert {s.key: s.count for s in a.service_countries} == {"DE": 2, "FR": 1, "IT": 1}
    assert a.providers[0].critical_services_without_exit_plan == 1


def test_data_gaps_are_visible_and_never_green() -> None:
    reg = build_valid_register()
    reg.b_02_01[0].annual_cost = None  # the only critical arrangement has no cost
    reg.b_05_01[0].hq_country = None
    reg.b_07_01[0].substitutability = None
    reg.add(Function(function_id="F-CASH", function_name="Cash management", entity_lei=ENTITY,
                     criticality=Criticality.CRITICAL, licensed_activity="Payment services",
                     last_assessment_date=date(2025, 6, 30)))
    a = analyse(reg, CFG)
    g = a.data_gaps
    assert (g.arrangements, g.without_cost, g.critical_without_cost) == (1, 1, 1)
    assert g.critical_spend_coverage == 0 and g.spend_coverage == 0
    assert g.critical_services_substitutability_unknown == 1
    assert g.providers_unknown_hq == 1 and g.critical_functions_without_service == 1
    cash = next(f for f in a.critical_functions if f.function_id == "F-CASH")
    assert cash.no_service and not cash.single_provider
    gap = next(k for k in a.key_findings if k.title.startswith("Data gaps"))
    assert gap.level is Level.HIGH and "not treated as harmless" in gap.detail
    report = validate(reg)
    pf = evaluate(reg, AssessmentBook())
    view = build_readiness(report=report, quality=quality_score(report), analysis=a,
                           portfolio=pf, plan=remediation_plan(pf), now=NOW, register=reg,
                           incidents=overview(IncidentLog(), reg, NOW))
    assert view.pillar("concentration").rag is Rag.RED  # cost unknown for all critical spend
    assert any("Complete the data behind" in x.text for x in view.actions)


def test_small_data_gap_is_amber_not_green() -> None:
    reg = build_valid_register()
    second_service(reg, exit_plan=True)
    reg.b_07_01[1].substitutability = None  # one of two critical services not assessed
    a = analyse(reg, CFG)
    assert a.data_gaps.any and a.data_gaps.critical_spend_coverage == 1
    gap = next(k for k in a.key_findings if k.title.startswith("Data gaps"))
    assert gap.level is Level.MEDIUM


def test_unknown_notice_period_is_not_day_zero() -> None:
    reg = build_valid_register()
    row = reg.b_02_02[0]
    row.end_date = NOW.date() + timedelta(days=200)
    row.notice_period_entity = None
    item = notice_schedule(reg, NOW.date())[0]
    assert item.status is NoticeStatus.UNKNOWN  # was "within a year", as if notice were 0
    row.notice_period_entity = 30
    assert notice_schedule(reg, NOW.date())[0].status is NoticeStatus.DUE_365
    row.notice_period_entity = None
    row.end_date = NOW.date() + timedelta(days=500)
    assert notice_schedule(reg, NOW.date())[0].status is NoticeStatus.LATER
    row.end_date = NOW.date() + timedelta(days=200)
    report = validate(reg)
    pf = evaluate(reg, AssessmentBook())
    view = build_readiness(report=report, quality=quality_score(report),
                           analysis=analyse(reg, AnalyticsConfig(reference_date=NOW.date())),
                           portfolio=pf, plan=remediation_plan(pf), now=NOW, register=reg,
                           incidents=overview(IncidentLog(), reg, NOW))
    texts = [x.text for x in view.actions if x.pillar == "contracts"]
    assert any("Record the notice period of 1" in x for x in texts)


def test_third_country_view_includes_switzerland() -> None:
    reg = build_valid_register()
    for p in reg.b_05_01:
        p.hq_country = "CH"
    a = analyse(reg, CFG)
    assert any("third countries (outside the EU/EEA, Switzerland included)" in k.title
               for k in a.key_findings)


def test_package_never_invents_lei_date_or_currency(tmp_path: Path) -> None:
    reg = build_valid_register()
    reg.b_01_02[0].currency = None  # no reporting currency for the maintaining entity
    with pytest.raises(ExportBlockedError) as exc:
        build_package_files(reg)
    assert exc.value.issues == ["the entity maintaining the register has no reporting "
                                "currency in B_01.02 (baseCurrency of all amounts)"]
    files, warnings = build_package_files(reg, XbrlCsvOptions(allow_incomplete=True))
    assert "baseCurrency,iso4217:EUR" in files["reports/parameters.csv"]
    assert any(w.startswith("DRAFT") for w in warnings)

    path = write_workbook(reg, tmp_path / "r.xlsx")
    runner = CliRunner()
    r = runner.invoke(main, ["export", str(path), "-o", str(tmp_path / "out")])
    assert r.exit_code == 2 and "Export refused" in r.output and "--allow-incomplete" in r.output
    r = runner.invoke(main, ["export", str(path), "-o", str(tmp_path / "out"),
                             "--allow-incomplete"])
    assert r.exit_code == 0 and "DRAFT" in r.output


def test_workbench_shows_package_problems(tmp_path: Path) -> None:
    client = TestClient(create_app(capacity=4))
    reg = build_valid_register()
    reg.b_01_02[0].currency = None
    path = write_workbook(reg, tmp_path / "r.xlsx")
    url = client.post("/import", files={"file": ("r.xlsx", path.read_bytes())},
                      follow_redirects=False).headers["location"]
    page = client.get(url + "/export")
    assert page.status_code == 200 and "data-package-blocked" in page.text
    assert "no reporting currency" in page.text and url + "/download/xbrl" not in page.text
    r = client.get(url + "/download/xbrl")
    assert r.status_code == 409
    ok = client.post("/sample", data={"variant": "clean"}, follow_redirects=False)
    url = ok.headers["location"]
    page = client.get(url + "/export").text
    assert "data-package-blocked" not in page and "/download/xbrl" in page
