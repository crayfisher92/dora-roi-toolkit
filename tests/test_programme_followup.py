"""Follow-up to the programme module review (docs/MODULE_REVIEW.md open items, P-31 …)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from dora_roi.contracts import (
    AssessmentBook,
    ComplianceStatus,
    ContractAssessment,
    evaluate,
    remediation_plan,
    write_assessment_workbook,
)
from dora_roi.contracts.analysis import contract_contexts
from dora_roi.contracts.provisions import PROVISIONS, Scope
from dora_roi.model import RegisterOfInformation
from dora_roi.model.codelists import Criticality
from dora_roi.sample import generate_sample, register_to_raw
from dora_roi.sample.programme import load_sample_programme
from dora_roi.web.app import create_app
from dora_roi.workspace import Workspace

from conftest import build_valid_register

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
ALL_2 = [p.id for p in PROVISIONS if p.scope is Scope.ALL]


def _register(criticality: Criticality | None, link: bool = True) -> RegisterOfInformation:
    reg = build_valid_register()
    reg.b_06_01[0].criticality = criticality
    if not link:
        reg.b_02_02[0].function_id = None
    return reg


def _art30_2_present(ref: str = "C-001") -> ContractAssessment:
    a = ContractAssessment(contract_ref=ref, assessor="T", assessed_on=date(2026, 11, 1))
    for pid in ALL_2:
        a.set(pid, "present", "Clause 1", "ok")
    return a


# =========================================================================== P-31 (A-A30-02)


@pytest.mark.parametrize(("criticality", "link", "scope"), [
    (Criticality.CRITICAL, True, "critical"),
    (Criticality.NOT_CRITICAL, True, "all"),
    (Criticality.NOT_ASSESSED, True, "unknown"),
    (None, True, "unknown"),
    (Criticality.CRITICAL, False, "unknown"),  # no function linked in B_02.02
])
def test_p31_criticality_state(criticality: Criticality | None, link: bool, scope: str) -> None:
    ctx = contract_contexts(_register(criticality, link))["C-001"]
    assert ctx.scope_key == scope
    assert ctx.full_checklist is (scope != "all")
    assert ctx.critical is (scope == "critical")


def test_p31_unknown_criticality_keeps_art_30_3_to_assess() -> None:
    book = AssessmentBook()
    book.save(_art30_2_present())
    # known not critical: Art. 30(2) complete = all checklist items present
    pf = evaluate(_register(Criticality.NOT_CRITICAL), book)
    assert pf.contracts[0].status is ComplianceStatus.COMPLIANT
    assert pf.criticality_unknown == []
    # unknown: the ten Art. 30(3) items stay on the checklist, not assessed
    pf = evaluate(_register(Criticality.NOT_ASSESSED), book)
    c = pf.contracts[0]
    assert c.status is ComplianceStatus.INCOMPLETE and c.unassessed == 10
    assert len(c.items) == len(PROVISIONS)
    assert [x.ref for x in pf.criticality_unknown] == ["C-001"]
    assert pf.critical_contracts == []  # not counted as critical (priorities, shares)
    plan = remediation_plan(pf, date(2026, 11, 23))
    assert [x.ref for x in plan.to_assess] == ["C-001"]
    # a gap on such an arrangement is not escalated to high
    a = _art30_2_present()
    a.set("30.3.d", "missing")
    book.save(a)
    plan = remediation_plan(evaluate(_register(None), book), date(2026, 11, 23))
    assert [(i.provision.id, i.priority.value) for i in plan.items] == [("30.3.d", "medium")]


def test_p31_workbook_template_lists_art_30_3_rows(tmp_path: Path) -> None:
    reg = _register(Criticality.NOT_ASSESSED)
    refs = {r: c.full_checklist for r, c in contract_contexts(reg).items()}
    path = write_assessment_workbook(AssessmentBook(), tmp_path / "a.xlsx", refs)
    rows = [r[1].value for r in load_workbook(path)["Assessments"].iter_rows(min_row=2)]
    assert "30.3.d" in rows and len(rows) == len(PROVISIONS)


def test_p31_web_and_readiness_show_unknown_criticality() -> None:
    ws = Workspace("s", register_to_raw(generate_sample().source_register), kind="sample")
    load_sample_programme(ws, NOW)
    unknown = [c.ref for c in ws.portfolio.criticality_unknown]
    assert unknown and "AR-AT-0063" in unknown
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "errors"},
                      follow_redirects=False).headers["location"]
    page = client.get(url + "/contract/AR-AT-0063").text
    assert "data-criticality-unknown" in page and "Criticality not assessed" in page
    assert 'id="pv-30_3_d"' in page  # the Art. 30(3) items are on the form
    assert "Criticality not assessed" in client.get(url + "/contracts").text
    report = client.get(url + "/readiness.html").text
    assert "whose criticality is not assessed" in report
    de = client.get(url + "/contract/AR-AT-0063?lang=de").text
    assert "Kritikalität nicht bewertet" in de


# =========================================================================== P-32 (RTS Art. 8(2))


def _sample_ws() -> Workspace:
    ws = Workspace("s", register_to_raw(generate_sample().source_register), kind="sample")
    load_sample_programme(ws, NOW)
    return ws


def test_p32_exempt_entities_take_a_recurring_series_out_of_readiness() -> None:
    from dora_roi.incidents import IncidentLog
    from dora_roi.incidents.report import overview, summary_dict, summary_markdown
    from dora_roi.readiness import Rag
    from dora_roi.web.programme_routes import workspace_readiness

    ws = _sample_ws()
    series = next(g for g in overview(ws.incidents, ws.register, NOW).recurring if g.major)
    leis = sorted({lei for i in series.incidents for lei in i.entity_leis})
    assert len(leis) == 2 and not series.exempt and series.reportable

    def pillar() -> object:
        return next(p for p in workspace_readiness(ws, "en", NOW).pillars
                    if p.key == "incidents")

    assert pillar().rag is Rag.RED  # type: ignore[attr-defined]
    # one of two entities exempt: a mixed series stays reportable (conservative)
    assert IncidentLog.model_validate(
        {"recurrence_exempt": [leis[0].lower(), f" {leis[0]} "]}).recurrence_exempt == [leis[0]]
    ws.incidents.recurrence_exempt = [leis[0].lower()]
    assert overview(ws.incidents, ws.register, NOW).recurring[0].reportable
    # all entities exempt: shown for information, not counted
    ws.incidents.recurrence_exempt = leis
    ov = overview(ws.incidents, ws.register, NOW)
    g = next(x for x in ov.recurring if x.key == series.key)
    assert g.major and g.exempt and not g.reportable
    assert ov.counts()["recurring_major"] == 0 and ov.counts()["recurring_exempt"] == 1
    p = pillar()
    assert p.rag is not Rag.RED  # type: ignore[attr-defined]
    assert any("declared exempt" in line for line in p.lines)  # type: ignore[attr-defined]
    data = summary_dict(ov, "UTC")
    assert data["recurring"][0]["exempt"] and not data["recurring"][0]["reportable"]
    assert "exempt, RTS Art. 8(2)" in summary_markdown(ov)
    # the declaration travels with the log (JSON, project file)
    again = IncidentLog.from_json(ws.incidents.to_json())
    assert again.recurrence_exempt == leis
    # without a declaration the field is not written (logs stay readable by 0.2.0-rc.1)
    assert "recurrence_exempt" not in IncidentLog().to_json()


def test_p32_settings_form_is_audited() -> None:
    client = TestClient(create_app())
    client.post("/user", data={"name": "Lena", "next": "/"})
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    page = client.get(url + "/incidents").text
    assert "RTS 2024/1772 Art. 8(2)" in page and 'name="exempt"' in page
    ws_leis = [x.split('"')[0] for x in page.split('name="exempt" value="')[1:]]
    r = client.post(url + "/incidents/settings",
                    data={"exempt_shown": "1", "exempt": [*ws_leis, "NOTANENTITY"]},
                    follow_redirects=False)
    assert r.status_code == 303 and "exempt_saved=1" in r.headers["location"]
    page = client.get(r.headers["location"]).text
    assert "Saved." in page and page.count("checked") >= len(ws_leis)
    assert "declared not to apply" in client.get(url + "/incidents/summary.html").text
    assert "RTS Art. 8(2)) not applied to" in client.get(url + "/audit").text
    # the time-zone form leaves the declaration alone
    client.post(url + "/incidents/settings", data={"timezone": "Europe/Zurich"})
    assert client.get(url + "/incidents").text.count('name="exempt" value=') == len(ws_leis)
    assert "NOTANENTITY" not in client.get(url + "/incidents/log.json").text
    de = client.get(url + "/incidents?lang=de").text
    assert "Regel zu wiederkehrenden Vorfällen" in de


# =========================================================================== P-33 / P-34 (scope)

LU_BANK = "6354ZX2X914MZGYMMB68"  # Alpenrand Banque Privée S.A. (Luxembourg, EU)


def test_p33_excluding_an_eu_entity_warns(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from dora_roi.cli import main
    from dora_roi.io.excel import write_workbook
    from dora_roi.scope import eea_entities, restrict_to_scope

    reg = generate_sample(inject_errors=False).source_register
    assert eea_entities(reg, {LU_BANK, "NOTALEI"}) == [LU_BANK]
    _, summary = restrict_to_scope(reg, {LU_BANK})
    assert summary.eea_excluded == [LU_BANK]
    # a non-EEA entity (e.g. the Swiss bank of a group) raises no warning
    reg.b_01_02[1].country = "CH"
    assert restrict_to_scope(reg, {LU_BANK})[1].eea_excluded == []
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    assert "data-scope-eea" not in client.get(url + "/finma").text
    page = client.get(client.post(url + "/scope", data={"out": [LU_BANK]},
                                  follow_redirects=False).headers["location"]).text
    assert "data-scope-eea" in page and "Alpenrand Banque Privée S.A.: located in the EU/EEA" \
        in page
    assert "mit Sitz in der EU" in client.get(url + "/finma?lang=de").text
    src = tmp_path / "reg.xlsx"
    write_workbook(generate_sample(inject_errors=False).source_register, src)
    for args in (["export", str(src), "-o", str(tmp_path / "p.zip"), "--format", "xbrl-csv"],
                 ["readiness", str(src), "-o", str(tmp_path / "r.html")]):
        res = CliRunner().invoke(main, [*args, "--exclude-entity", LU_BANK])
        assert res.exit_code == 0, res.output
        assert "located in the EU/EEA" in res.output


def test_p34_dora_pillars_count_only_the_scope() -> None:
    from dora_roi.incidents import Answers, Incident
    from dora_roi.scope import incidents_in_scope
    from dora_roi.web.programme_routes import workspace_readiness

    ws = _sample_ws()
    ws.incidents.save(Incident(id="INC-LU-1", title="LU only", detected_at=NOW,
                               entity_leis=[LU_BANK], answers=Answers()), "created")
    ws.incidents.save(Incident(id="INC-NONE", title="no entity", detected_at=NOW,
                               answers=Answers()), "created")
    full = ws.portfolio
    assert ws.dora_portfolio() is full  # no scope: same object
    with ws.lock:
        ws.out_of_scope = {LU_BANK}
        ws.programme_changed("scope", "B_01.02", "x")
    scoped = ws.dora_portfolio()
    assert scoped is ws.dora_portfolio()  # cached
    left_out = {c.ref for c in full.contracts} - {c.ref for c in scoped.contracts}
    assert left_out and all(ref.startswith(("AR-LU", "CO-LU")) for ref in left_out)
    log, n = incidents_in_scope(ws.incidents, {LU_BANK})
    assert n == 1 and "INC-LU-1" not in log.incidents and "INC-NONE" in log.incidents
    assert incidents_in_scope(ws.incidents, set()) == (ws.incidents, 0)
    view = workspace_readiness(ws, "en", NOW)
    lines = {p.key: p.lines for p in view.pillars}
    assert any(f"{len(left_out)} arrangement(s) used only by entities outside" in x
               for x in lines["contracts"])
    assert any("1 incident(s) concerning only entities outside" in x
               for x in lines["incidents"])
    assert view.portfolio is scoped
    # FINMA keeps the whole dataset
    assert ws.portfolio is full or len(ws.portfolio.contracts) == len(full.contracts)
    # changing the scope back invalidates the cached DORA view
    ws.replace_programme(out_of_scope=set())
    assert ws.dora_portfolio() is ws.portfolio


# =========================================================================== P-27


def test_p27_by_provider_sheet_shows_remediation_progress(tmp_path: Path) -> None:
    from dora_roi.contracts.report import write_plan_workbook

    ws = _sample_ws()
    plan = remediation_plan(ws.portfolio, date(2026, 11, 23))
    path = write_plan_workbook(plan, tmp_path / "plan.xlsx")
    sheet = load_workbook(path)["By provider"]
    header = [c.value for c in sheet[1]]
    rows = {r[0].value: [c.value for c in r] for r in sheet.iter_rows(min_row=2)
            if r[0].value}
    for col in ("Remediation actions", "Not started", "Planned", "In negotiation",
                "Agreed, awaiting signature", "Past target date"):
        assert col in header, col
    helix = rows["Helix Core Banking AG"]
    assert helix[header.index("In negotiation")] == 2
    assert helix[header.index("Remediation actions")] == sum(
        1 for i in plan.items if i.providers == "Helix Core Banking AG")
    ledger = rows["Ledgerline Systems GmbH"]
    assert ledger[header.index("Planned")] == 1
    assert ledger[header.index("Past target date")] >= 1  # agreed date 30 Sep 2026 passed
    total = sum(r[header.index("Remediation actions")] for r in rows.values())
    assert total >= len(plan.items)  # an action counts for every provider of its contract
    de = load_workbook(write_plan_workbook(plan, tmp_path / "de.xlsx", lang="de"))
    assert "Nach Zieltermin" in [c.value for c in de["Nach Dienstleister"][1]]
