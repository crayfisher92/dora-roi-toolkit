"""DORA readiness: traffic lights per pillar, priority actions, executive report."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from click.testing import CliRunner

from dora_roi.analytics import analyse
from dora_roi.cli import main
from dora_roi.contracts import AssessmentBook, ContractAssessment, evaluate, remediation_plan
from dora_roi.contracts.provisions import PROVISIONS
from dora_roi.finma import evaluate_finma
from dora_roi.incidents import Answers, Incident, IncidentLog
from dora_roi.incidents.report import overview
from dora_roi.model import RegisterOfInformation
from dora_roi.quality import quality_score
from dora_roi.readiness import Rag, ReadinessView, build_readiness, render_readiness_html
from dora_roi.sample import generate_sample
from dora_roi.sample.assessments import sample_assessments
from dora_roi.sample.incidents import sample_incidents
from dora_roi.validation import validate

from conftest import build_valid_register

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def view_for(reg: RegisterOfInformation, book: AssessmentBook | None = None,
             log: IncidentLog | None = None, finma: bool = True,
             lang: str = "en") -> ReadinessView:
    report = validate(reg)
    pf = evaluate(reg, book or AssessmentBook())
    lg = log or IncidentLog()
    return build_readiness(
        report=report, quality=quality_score(report), analysis=analyse(reg), portfolio=pf,
        plan=remediation_plan(pf, NOW.date()), incidents=overview(lg, reg, NOW),
        finma=evaluate_finma(reg, pf, lg, NOW) if finma else None, lang=lang, now=NOW)


def compliant_book() -> AssessmentBook:
    book = AssessmentBook()
    a = ContractAssessment(contract_ref="C-001")
    for p in PROVISIONS:
        a.set(p.id, "present")
    book.save(a)
    return book


def test_sample_is_red_with_actions() -> None:
    reg = generate_sample().register
    v = view_for(reg, sample_assessments(reg), sample_incidents(reg, NOW))
    rags = {p.key: p.rag for p in v.pillars}
    assert rags == {"register": Rag.RED, "contracts": Rag.RED, "incidents": Rag.RED,
                    "concentration": Rag.RED, "finma": Rag.AMBER}
    assert v.overall is Rag.RED and v.pillar("finma").metric == "56%"
    texts = [a.text for a in v.actions]
    assert any("blocking validation error" in t for t in texts)
    assert any("kronos-certificate-rotation" in t for t in texts)
    assert any("Initial notification for INC-2026-014" in t for t in texts)
    assert [a.priority for a in v.actions] == sorted(
        (a.priority for a in v.actions), key=["high", "medium", "low"].index)


def test_clean_register_green_and_grey() -> None:
    reg = build_valid_register()
    v = view_for(reg, compliant_book(), finma=False)
    rags = {p.key: p.rag for p in v.pillars}
    assert rags["register"] is Rag.GREEN and rags["contracts"] is Rag.GREEN
    assert rags["incidents"] is Rag.GREY  # nothing recorded
    assert "finma" not in rags and v.overall in (Rag.GREEN, Rag.AMBER, Rag.RED)
    empty = view_for(RegisterOfInformation(), finma=False)
    assert {p.key: p.rag for p in empty.pillars}["register"] is Rag.GREY
    assert {p.key: p.rag for p in empty.pillars}["contracts"] is Rag.GREY
    assert {p.key: p.rag for p in empty.pillars}["concentration"] is Rag.GREY
    assert empty.overall is Rag.GREY


def test_contract_and_incident_amber_rules() -> None:
    reg = build_valid_register()
    book = compliant_book()
    a = book.get("C-001")
    assert a is not None
    a.set("30.2.e", "partial")  # medium priority only
    v = view_for(reg, book)
    assert v.pillar("contracts").rag is Rag.AMBER
    a.set("30.3.d", "missing")
    assert view_for(reg, book).pillar("contracts").rag is Rag.RED
    log = IncidentLog()
    log.save(Incident(id="I-1", title="t", detected_at=NOW - timedelta(hours=1),
                      answers=Answers(critical_services=True, malicious_access=True)),
             "created")
    v = view_for(reg, compliant_book(), log)
    assert v.pillar("incidents").rag is Rag.AMBER  # major, initial notification pending
    assert any(x.pillar == "incidents" and x.priority == "high" for x in v.actions)
    late = IncidentLog()
    late.save(Incident(id="I-2", title="t", detected_at=NOW - timedelta(days=3),
                       classified_at=NOW - timedelta(days=3),
                       answers=Answers(critical_services=True, malicious_access=True)),
              "created")
    v = view_for(reg, compliant_book(), late)
    assert v.pillar("incidents").rag is Rag.RED and "overdue" in v.pillar("incidents").lines[1]
    open_q = IncidentLog()
    open_q.save(Incident(id="I-3", title="t", detected_at=NOW), "created")
    assert view_for(reg, compliant_book(), open_q).pillar("incidents").rag is Rag.AMBER
    ok = IncidentLog()
    ok.save(Incident(id="I-4", title="t", detected_at=NOW,
                     answers=Answers(critical_services=False)), "created")
    assert view_for(reg, compliant_book(), ok).pillar("incidents").rag is Rag.GREEN


def test_readiness_report_html() -> None:
    reg = generate_sample().register
    v = view_for(reg, sample_assessments(reg), sample_incidents(reg, NOW))
    html = render_readiness_html(v, client="Alpenrand Group", prepared_by="GRC")
    assert "DORA readiness report" in html and "Alpenrand Group" in html
    assert "Priority actions" in html and "@page" in html and "<svg" in html
    assert "FIN-OS-05" in html and "Templates with most errors" in html
    de = render_readiness_html(view_for(reg, lang="de"), lang="de")
    assert 'lang="de"' in de and "DORA-Statusbericht" in de and "Prioritäre Maßnahmen" in de
    bare = render_readiness_html(view_for(build_valid_register(), compliant_book(),
                                          finma=False))
    assert "Priority actions" in bare
    assert "Switzerland – FINMA coverage" not in bare


def test_cli_readiness(tmp_path: Path) -> None:
    runner = CliRunner()
    reg = tmp_path / "s.xlsx"
    runner.invoke(main, ["sample", str(reg), "--assessments", str(tmp_path / "a.json"),
                         "--incidents", str(tmp_path / "i.json")])
    r = runner.invoke(main, ["readiness", str(reg), "--assessments", str(tmp_path / "a.json"),
                             "--incidents", str(tmp_path / "i.json"), "-o",
                             str(tmp_path / "r.html"), "--json", str(tmp_path / "r.json"),
                             "--client", "Alpenrand", "--now", "2026-01-15T12:00"])
    assert r.exit_code == 0, r.output
    assert "Overall: red" in r.output
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["overall"] == "red" and len(data["pillars"]) == 5 and data["actions"]
    r = runner.invoke(main, ["readiness", str(reg), "-o", str(tmp_path / "r2.html"),
                             "--no-finma", "--lang", "de"])
    assert r.exit_code == 0 and "finma" not in r.output
    assert "DORA-Statusbericht" in (tmp_path / "r2.html").read_text()
