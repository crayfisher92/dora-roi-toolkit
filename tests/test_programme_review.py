"""Regression tests for the programme review cycles (docs/BACKLOG.md, P-xx)."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from dora_roi.cli import main
from dora_roi.contracts import (
    AssessmentBook,
    ComplianceStatus,
    ContractAssessment,
    ProvisionStatus,
    evaluate,
    read_assessment_workbook,
    remediation_plan,
    write_assessment_workbook,
)
from dora_roi.contracts.consistency import consistency_hints
from dora_roi.contracts.provisions import PROVISIONS
from dora_roi.contracts.suggest import suggest
from dora_roi.incidents import Answers, Incident, IncidentLog, RootCause
from dora_roi.incidents.classify import possible_recurrences
from dora_roi.io.excel import write_workbook
from dora_roi.project import ProjectError, load_project, save_project
from dora_roi.readiness import Rag, build_readiness
from dora_roi.sample import generate_sample, register_to_raw
from dora_roi.sample.contract_docs import SAMPLE_CONTRACT_TEXT
from dora_roi.sample.programme import load_sample_programme
from dora_roi.web.app import create_app
from dora_roi.workspace import Workspace

from conftest import PROVIDER, build_valid_register

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def sample_ws() -> Workspace:
    ws = Workspace("s", register_to_raw(generate_sample().source_register), kind="sample")
    load_sample_programme(ws, NOW)
    return ws


def present_except(ref: str, **gaps: str) -> ContractAssessment:
    a = ContractAssessment(contract_ref=ref)
    for p in PROVISIONS:
        a.set(p.id, gaps.get(p.id.replace(".", "_"), "present"))
    return a


# =========================================================================== P-01 / P-02


def test_p01_project_files_keep_programme_data(tmp_path: Path) -> None:
    ws = sample_ws()
    path = save_project(ws, tmp_path / "a.roiproj")
    again = load_project(path)
    assert len(again.contracts) == len(ws.contracts) == 13
    assert again.contracts.get("AR-DE-0057") == ws.contracts.get("AR-DE-0057")
    assert len(again.incidents) == 5 and again.incidents.timezone == "Europe/Berlin"
    assert again.portfolio.counts() == ws.portfolio.counts()
    # files written before the programme table existed still open
    con = sqlite3.connect(path)
    con.execute("DROP TABLE programme")
    con.commit()
    con.close()
    assert len(load_project(path).contracts) == 0
    # tampered programme data is rejected
    path = save_project(ws, tmp_path / "b.roiproj")
    con = sqlite3.connect(path)
    con.execute("UPDATE programme SET data = '{\"schema\": \"x\"}' WHERE key = 'contracts'")
    con.commit()
    con.close()
    with pytest.raises(ProjectError, match="programme"):
        load_project(path)


def test_p02_programme_changes_are_audited_and_autosaved() -> None:
    ws = sample_ws()
    calls: list[int] = []
    ws.on_change = lambda w: calls.append(1)
    before = len(ws.changes)
    ws.programme_changed("art30", "AR-DE-0013", "Assessment created", "Lena")
    assert calls == [1] and len(ws.changes) == before + 1
    ch = ws.changes[-1]
    assert (ch.kind, ch.template, ch.column, ch.user) == ("art30", "Art. 30", "AR-DE-0013",
                                                          "Lena")
    # register reconstruction ignores programme entries
    assert ws.raw_at(ws.versions[-1].number) is not None


def test_p02_web_audit_trail_and_autosave(tmp_path: Path) -> None:
    client = TestClient(create_app(projects_dir=tmp_path))
    client.post("/user", data={"name": "Lena", "next": "/"})
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    client.post(url + "/contract/AR-DE-0013", data={"action": "save", "st-30.1": "present"})
    client.post(url + "/incidents/new", data={"title": "t", "detected_at": "2025-12-01T09:00"})
    audit = client.get(url + "/audit").text
    assert "Art. 30 contract assessment" in audit and "Incident log" in audit and "Lena" in audit
    csv = client.get(url + "/download/audit.csv").text
    assert "art30" in csv and "incident" in csv
    saved = list(tmp_path.glob("*.roiproj"))
    assert len(saved) == 1
    reopened = load_project(saved[0])
    assert reopened.contracts.get("AR-DE-0013") is not None
    assert reopened.contracts.get("AR-DE-0013").assessor == "Lena"  # type: ignore[union-attr]
    assert len(reopened.incidents) == 6


# =========================================================================== P-03 / P-04


def test_p03_concurrent_saves_keep_every_history_entry() -> None:
    ws = sample_ws()

    def work(n: int) -> None:
        for i in range(10):
            with ws.lock:
                a = present_except("AR-DE-0013")
                a.notes = f"{n}-{i}"
                ws.contracts.save(a)
                ws.programme_changed("art30", "AR-DE-0013", "x")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(ws.contracts.get("AR-DE-0013").history) == 80  # type: ignore[union-attr]


def test_p04_portfolio_is_cached_and_invalidated() -> None:
    ws = sample_ws()
    first = ws.portfolio
    assert ws.portfolio is first
    ws.programme_changed("art30", "x", "y")
    second = ws.portfolio
    assert second is not first
    ws.edit("B_02.01", ws.raw.tables["B_02.01"].rows[0].row or 4, "c0050", "1")
    assert ws.portfolio is not second


# =========================================================================== P-05


@pytest.mark.parametrize("field", ["occurred_at", "classified_at", "resolved_at",
                                   "initial_submitted_at", "final_submitted_at"])
def test_p05_incident_chronology_is_enforced(field: str) -> None:
    good = {"id": "I", "title": "t", "detected_at": NOW}
    bad = {"occurred_at": NOW + timedelta(hours=1), "classified_at": NOW - timedelta(hours=1),
           "resolved_at": NOW - timedelta(days=1), "initial_submitted_at": NOW - timedelta(
               minutes=1), "final_submitted_at": NOW}
    extra: dict[str, object] = {field: bad[field]}
    if field == "final_submitted_at":
        extra["intermediate_submitted_at"] = NOW + timedelta(days=2)
    with pytest.raises(ValueError, match=field.replace("final", "final")):
        Incident.model_validate(good | extra)
    Incident.model_validate(good | {"occurred_at": NOW, "classified_at": NOW,
                                    "resolved_at": NOW})


def test_p05_web_rejects_out_of_order_times(tmp_path: Path) -> None:
    client = TestClient(create_app())
    path = write_workbook(build_valid_register(), tmp_path / "r.xlsx")
    url = client.post("/import", files={"file": ("r.xlsx", path.read_bytes())},
                      follow_redirects=False).headers["location"]
    for field, value in (("occurred_at", "2025-12-02T09:00"), ("classified_at",
                                                               "2025-11-30T09:00"),
                         ("resolved_at", "2025-11-01T09:00")):
        r = client.post(url + "/incidents/new", data={"title": "t",
                                                      "detected_at": "2025-12-01T09:00",
                                                      field: value})
        assert r.status_code == 400 and "Please check" in r.text, field
    r = client.post(url + "/incidents/new", data={"title": "t", "detected_at": "2025-12-01T09:00",
                                                  "a-critical_services": "yes",
                                                  "a-malicious_access": "yes"},
                    follow_redirects=False)
    loc = r.headers["location"].split("?")[0]
    r = client.post(loc, data={"action": "report", "kind": "initial",
                               "submitted_at": "2025-11-30T09:00"})
    assert r.status_code == 400 and "submission time" in r.text


# =========================================================================== P-06


def test_p06_time_bound_exceptions() -> None:
    reg = build_valid_register()
    book = AssessmentBook()
    a = present_except("C-001", **{"30_3_e_i": "partial"})
    item = a.items["30.3.e.i"]
    a.items["30.3.e.i"] = item.model_copy(update={
        "exception_reason": "Pooled audit", "exception_approver": "CRO",
        "exception_until": date(2026, 6, 30)})
    book.save(a)
    pf = evaluate(reg, book, date(2026, 1, 1))
    c = pf.contracts[0]
    assert c.status is ComplianceStatus.EXCEPTION and not c.gaps and len(c.exceptions) == 1
    assert c.partial == 1  # truthful counts
    plan = remediation_plan(pf, date(2026, 1, 1))
    assert plan.items == [] and plan.exceptions[0].until == date(2026, 6, 30)
    expired = evaluate(reg, book, date(2026, 7, 1)).contracts[0]
    assert expired.status is ComplianceStatus.GAPS
    assert expired.items[[p.id for p in PROVISIONS].index("30.3.e.i")].exception_expired
    # a present clause cannot carry a valid exception
    item = a.items["30.3.e.i"]
    a.items["30.3.e.i"] = item.model_copy(update={"status": ProvisionStatus.PRESENT})
    assert not a.items["30.3.e.i"].exception_valid(date(2026, 1, 1))


def test_p06_exception_round_trip_form_and_workbook(tmp_path: Path) -> None:
    book = AssessmentBook()
    a = ContractAssessment(contract_ref="C-001")
    a.set("30.3.d", "missing", exception=("Pooled TLPT next year", "CRO", date(2026, 12, 31)))
    book.save(a)
    path = write_assessment_workbook(book, tmp_path / "a.xlsx", {"C-001": True})
    assert "exception_until" in [c.value for c in load_workbook(path)["Assessments"][1]]
    again, problems = read_assessment_workbook(path)
    assert problems == []
    assert again.get("C-001").item("30.3.d").exception_until == date(2026, 12, 31)  # type: ignore
    client = TestClient(create_app())
    reg = write_workbook(build_valid_register(), tmp_path / "r.xlsx")
    url = client.post("/import", files={"file": ("r.xlsx", reg.read_bytes())},
                      follow_redirects=False).headers["location"]
    form = {"action": "save", "st-30.3.d": "missing", "exr-30.3.d": "Pooled TLPT",
            "exa-30.3.d": "CRO", "exu-30.3.d": "2099-12-31"}
    assert client.post(url + "/contract/C-001", data=form,
                       follow_redirects=False).status_code == 303
    page = client.get(url + "/contract/C-001")
    assert "Exception until 2099-12-31" in page.text and "Pooled TLPT" in page.text
    client.post(url + "/contract/C-001", data=dict(form, **{"exu-30.3.d": "2099-06-30"}))
    assert "30.3.d: exception until 2099-06-30 approved by CRO" in client.get(
        url + "/contract/C-001").text
    plan = client.get(url + "/contracts/plan.html").text
    assert "Approved exceptions" in plan and "Pooled TLPT" in plan
    assert 'value="exception" selected' in client.get(url + "/contracts?status=exception").text
    bad = dict(form, **{"exu-30.3.d": ""})
    assert client.post(url + "/contract/C-001", data=bad).status_code == 400
    present = dict(form, **{"st-30.3.d": "present"})
    assert client.post(url + "/contract/C-001", data=present).status_code == 400


# =========================================================================== P-07


def test_p07_concentration_pillar_ignores_contract_lifecycle() -> None:
    ws = sample_ws()
    from dora_roi.web.programme_routes import workspace_readiness

    rd = workspace_readiness(ws, "en", NOW)
    conc = [a for a in rd.actions if a.pillar == "concentration"]
    assert all("expire" not in a.text and "notice" not in a.text for a in conc)
    contracts = [a.text for a in rd.actions if a.pillar == "contracts"]
    assert any("before their notice deadline (MSA-DE-0001)" in t for t in contracts)
    assert any("expiring arrangement" in t for t in contracts)
    de = workspace_readiness(ws, "de", NOW)
    assert any("Ersetzbarkeit und Ausstieg" in a.text for a in de.actions)
    assert "nicht konzentriert" in de.pillar("concentration").lines[0]


def test_p07_concentration_rules_on_small_register() -> None:
    from dora_roi.analytics import analyse
    from dora_roi.incidents.report import overview
    from dora_roi.quality import quality_score
    from dora_roi.validation import validate

    reg = build_valid_register()
    report = validate(reg)
    pf = evaluate(reg, AssessmentBook())
    view = build_readiness(report=report, quality=quality_score(report), analysis=analyse(reg),
                           portfolio=pf, plan=remediation_plan(pf), now=NOW, register=reg,
                           incidents=overview(IncidentLog(), reg, NOW))
    # one provider group with 100 % of spend → red, with a translated action
    assert view.pillar("concentration").rag is Rag.RED
    assert any("of ICT spend" in a.text for a in view.actions)


# =========================================================================== P-08 / P-09


def test_p08_pdf_downloads_and_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "dirty"},
                      follow_redirects=False).headers["location"]
    from dora_roi.reporting.pdf import pdf_available

    for path in ("/readiness.pdf", "/contracts/plan.pdf", "/incidents/summary.pdf"):
        r = client.get(url + path)
        if pdf_available():
            assert r.status_code == 200 and r.content[:5] == b"%PDF-", path
    assert ("readiness.pdf" in client.get(url + "/dashboard").text) is pdf_available()
    monkeypatch.setattr("dora_roi.web.programme_routes.pdf_available", lambda: False)
    assert client.get(url + "/readiness.pdf").status_code == 404
    runner = CliRunner()
    reg = tmp_path / "s.xlsx"
    runner.invoke(main, ["sample", str(reg)])
    if pdf_available():
        r = runner.invoke(main, ["readiness", str(reg), "-o", str(tmp_path / "r.pdf")])
        assert r.exit_code == 0 and (tmp_path / "r.pdf").read_bytes()[:5] == b"%PDF-"
    from dora_roi.reporting.pdf import PdfUnavailableError

    def unavailable(html: str) -> bytes:
        raise PdfUnavailableError("no weasyprint")

    monkeypatch.setattr("dora_roi.reporting.pdf.html_to_pdf", unavailable)
    r = runner.invoke(main, ["readiness", str(reg), "-o", str(tmp_path / "x.pdf")])
    assert r.exit_code == 1 and "no weasyprint" in r.output


def test_p09_programme_reports_use_report_csp() -> None:
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    for path in ("/contracts/plan.html", "/incidents/summary.html", "/readiness.html"):
        assert client.get(url + path).headers["content-security-policy"].startswith(
            "default-src 'none'"), path
    assert "default-src 'self'" in client.get(url + "/contracts").headers[
        "content-security-policy"]


# =========================================================================== P-10 – P-12


def test_p10_snippet_stays_in_clause() -> None:
    snippet = suggest(SAMPLE_CONTRACT_TEXT).by_id()["30.3.e.i"].snippet
    assert snippet.startswith("12. Audit") and "awareness" not in snippet


def test_p11_consistency_hints() -> None:
    ws = sample_ws()
    pf = ws.portfolio
    hints = {c.ref: consistency_hints(ws.register, c) for c in pf.contracts}
    keys = {(ref, h.key) for ref, hs in hints.items() for h in hs}
    assert ("AR-DE-0026", "subcontractors") in keys and ("AR-DE-0022", "exit_plan") in keys
    assert ("AR-DE-0014", "notice") in keys
    reg = build_valid_register()
    reg.b_07_01[0].last_audit_date = None
    book = AssessmentBook()
    a = present_except("C-001", **{"30_2_b_1": "missing"})
    book.save(a)
    hs = consistency_hints(reg, evaluate(reg, book).contracts[0])
    assert {h.key for h in hs} == {"locations", "no_audit"}
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    assert "Register and contract disagree" in client.get(url + "/contract/AR-DE-0026").text


def test_p12_possible_recurring_incidents() -> None:
    log = IncidentLog()
    for i, days in enumerate((10, 40)):
        log.save(Incident(id=f"I-{i}", title="t", detected_at=NOW - timedelta(days=days),
                          provider_codes=[PROVIDER], root_cause=RootCause.SYSTEM,
                          recurrence_key="a" if i else "",
                          answers=Answers(critical_services=False)), "created")
    found = possible_recurrences(log, NOW)
    assert len(found) == 1 and found[0].incidents == ("I-1", "I-0")
    same = IncidentLog()
    for i in range(2):
        same.save(Incident(id=f"J-{i}", title="t", detected_at=NOW - timedelta(days=i),
                           provider_codes=[PROVIDER], root_cause=RootCause.SYSTEM,
                           recurrence_key="k", answers=Answers(critical_services=False)),
                  "created")
    assert possible_recurrences(same, NOW) == []
