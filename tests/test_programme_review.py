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


# =========================================================================== cycle 2


def _docx(members: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_p13_malformed_docx_is_a_clean_error() -> None:
    from dora_roi.contracts.extract import ExtractionError, extract_text

    xml = (b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/'
           b'main"><w:body><w:p><w:r><w:t>Audit rights</w:t></w:r></w:p></w:body></w:document>')
    good = _docx({"word/document.xml": xml})
    assert "Audit rights" in extract_text("c.docx", good).text
    # corrupt the CRC of the member (local header and central directory)
    bad = bytearray(good)
    for sig in (b"PK\x03\x04", b"PK\x01\x02"):
        pos = bad.find(sig)
        crc_at = pos + (14 if sig == b"PK\x03\x04" else 16)
        bad[crc_at:crc_at + 4] = b"\x00\x00\x00\x00"
    with pytest.raises(ExtractionError, match="corrupt"):
        extract_text("c.docx", bytes(bad))
    # the web upload answers with a form error instead of a 500
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    r = client.post(url + "/contract/AR-DE-0013", data={"action": "suggest"},
                    files={"file": ("c.docx", bytes(bad), "application/octet-stream")})
    assert r.status_code == 400 and "corrupt" in r.text


def test_p14_import_keeps_history() -> None:
    book = AssessmentBook()
    a = present_except("C-1")
    book.save(a, by="Lena", at=NOW - timedelta(days=2))
    a2 = present_except("C-1", **{"30_2_h": "missing"})
    book.save(a2, by="Lena", at=NOW - timedelta(days=1))
    exported = AssessmentBook.from_json(book.to_json())
    exported.assessments["C-1"] = present_except("C-1", **{"30_2_h": "partial"})
    assert book.merge(exported, source="client.xlsx", by="Max", at=NOW) == (0, 1)
    hist = book.get("C-1").history  # type: ignore[union-attr]
    assert [e.by for e in hist] == ["Lena", "Lena", "Max"]
    assert "client.xlsx" in hist[-1].summary and "30.2.h: missing → partial" in hist[-1].summary
    assert book.get("C-1").item("30.2.h").status is ProvisionStatus.PARTIAL  # type: ignore
    # importing the same file twice does not duplicate the imported history
    book2 = AssessmentBook.from_json(book.to_json())
    book.merge(book2, at=NOW + timedelta(hours=1))
    assert len(book.get("C-1").history) == 4  # type: ignore[union-attr]

    log = IncidentLog()
    inc = Incident(id="I-1", title="t", detected_at=NOW - timedelta(days=1))
    log.save(inc, "created", by="Lena", at=NOW - timedelta(days=1))
    log.save(inc.model_copy(update={"title": "t2"}), "updated", by="Lena", at=NOW)
    other = IncidentLog.from_json(log.to_json())
    other.incidents["I-1"] = other.incidents["I-1"].model_copy(update={"title": "t3",
                                                                       "history": []})
    assert log.merge(other, source="log.json", by="Max", at=NOW) == (0, 1)
    assert [e.action for e in log.get("I-1").history] == [  # type: ignore[union-attr]
        "created", "updated", "imported"]
    assert log.get("I-1").title == "t3"  # type: ignore[union-attr]


SWISS_LIKE = "6354ZX2X914MZGYMMB68"  # the sample's Luxembourg bank stands in for a Swiss one


def test_p15_restrict_to_scope() -> None:
    from dora_roi.scope import ScopeError, restrict_to_scope
    from dora_roi.validation.engine import validate

    reg = generate_sample(inject_errors=False).source_register
    same, summary = restrict_to_scope(reg, set())
    assert same is reg and summary.total_removed == 0
    out, summary = restrict_to_scope(reg, {SWISS_LIKE})
    assert SWISS_LIKE not in {e.lei for e in out.b_01_02}
    assert all(s.entity_lei != SWISS_LIKE for s in out.b_02_02)
    assert summary.removed["B_02.01"] > 0 and summary.removed["B_01.02"] == 1
    # arrangements shared with in-scope entities stay
    shared = {s.contract_ref for s in reg.b_02_02 if s.entity_lei == SWISS_LIKE} & {
        s.contract_ref for s in reg.b_02_02 if s.entity_lei != SWISS_LIKE}
    assert shared <= {c.contract_ref for c in out.b_02_01}
    # the restricted register is still a valid submission
    assert validate(out).errors == []
    assert len(reg.b_01_02) == 3  # the original is untouched
    with pytest.raises(ScopeError):
        restrict_to_scope(reg, {reg.maintainer.lei})  # type: ignore[union-attr]


def test_p15_scope_in_web_project_and_cli(tmp_path: Path) -> None:
    import io
    import zipfile

    client = TestClient(create_app())
    client.post("/user", data={"name": "Lena", "next": "/"})
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    page = client.get(url + "/finma").text
    assert "DORA reporting scope" in page and 'value="' + SWISS_LIKE + '"' in page
    full = zipfile.ZipFile(io.BytesIO(client.get(url + "/download/xbrl").content))
    r = client.post(url + "/scope", data={"out": [SWISS_LIKE, "UNKNOWNLEI"]},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "Scope saved" in page and "left out of the supervisory package" in page
    assert "outside the DORA scope are left out" in client.get(url + "/export").text
    part = zipfile.ZipFile(io.BytesIO(client.get(url + "/download/xbrl").content))

    def b0102(z: zipfile.ZipFile) -> str:
        name = next(n for n in z.namelist() if n.endswith("b_01.02.csv"))
        return z.read(name).decode()

    assert SWISS_LIKE in b0102(full) and SWISS_LIKE not in b0102(part)
    assert "DORA reporting scope" in client.get(url + "/audit").text
    # the maintainer cannot be excluded via the form either
    maintainer = generate_sample().source_register.maintainer.lei  # type: ignore[union-attr]
    client.post(url + "/scope", data={"out": [maintainer]})
    page = client.get(url + "/finma").text
    assert f'value="{maintainer}" checked' not in page and f'value="{SWISS_LIKE}" checked' \
        not in page
    # project round trip
    ws = sample_ws()
    ws.out_of_scope = {SWISS_LIKE}
    again = load_project(save_project(ws, tmp_path / "s.roiproj"))
    assert again.out_of_scope == {SWISS_LIKE}
    assert SWISS_LIKE not in {e.lei for e in again.dora_register().b_01_02}
    # CLI
    src = tmp_path / "reg.xlsx"
    write_workbook(generate_sample(inject_errors=False).source_register, src)
    out = tmp_path / "pkg.zip"
    res = CliRunner().invoke(main, ["export", str(src), "-o", str(out), "--format",
                                    "xbrl-csv", "--exclude-entity", SWISS_LIKE.lower()])
    assert res.exit_code == 0, res.output
    assert "Outside the DORA scope" in res.output
    assert SWISS_LIKE not in b0102(zipfile.ZipFile(out))
    maint = generate_sample().source_register.maintainer.lei  # type: ignore[union-attr]
    res = CliRunner().invoke(main, ["export", str(src), "-o", str(out), "--format",
                                    "xbrl-csv", "--exclude-entity", maint])
    assert res.exit_code != 0 and "maintaining" in res.output
    res = CliRunner().invoke(main, ["export", str(src), "-o", str(tmp_path / "x.xlsx"),
                                    "--format", "excel", "--exclude-entity", SWISS_LIKE])
    assert res.exit_code == 0 and "only applies" in res.output


def test_p15_invalid_scope_in_project_is_rejected(tmp_path: Path) -> None:
    path = save_project(sample_ws(), tmp_path / "a.roiproj")
    con = sqlite3.connect(path)
    con.execute("UPDATE programme SET data = '{\"out_of_scope\": [1]}' WHERE key = 'scope'")
    con.commit()
    con.close()
    with pytest.raises(ProjectError, match="programme"):
        load_project(path)


def test_p16_remediation_progress() -> None:
    from dora_roi.contracts import RemediationProgress

    assert RemediationProgress.parse("In Verhandlung") is RemediationProgress.NEGOTIATING
    assert RemediationProgress.parse("") is None and RemediationProgress.parse("offen") is None
    with pytest.raises(ValueError, match="remediation"):
        RemediationProgress.parse("maybe")
    ws = sample_ws()
    plan = remediation_plan(ws.portfolio, date(2026, 11, 5))
    pr = plan.progress_counts()
    assert pr["negotiating"] == 2 and pr["agreed"] == 1 and pr["planned"] == 1
    assert sum(pr.values()) == len(plan.items)
    overdue = plan.overdue()
    assert [(i.contract_ref, i.provision.id) for i in overdue] == [("AR-DE-0026", "30.2.a.2")]
    item = next(i for i in plan.items if (i.contract_ref, i.provision.id)
                == ("MSA-DE-0010", "30.3.d"))
    assert item.target_date == date(2026, 12, 31) and item.owner
    assert not item.overdue(date(2027, 6, 1))  # agreed items are never overdue
    proposed = next(i for i in plan.items if i.progress is None)
    assessed = ws.contracts.get(proposed.contract_ref).assessed_on  # type: ignore[union-attr]
    assert proposed.due is None and proposed.target_date == assessed + timedelta(days=90)
    # P-22: the proposed date does not move with the plan date, and passing it is visible
    later = remediation_plan(ws.portfolio, date(2027, 1, 1))
    same = next(i for i in later.items if (i.contract_ref, i.provision.id)
                == (proposed.contract_ref, proposed.provision.id))
    assert same.target_date == proposed.target_date and same.late(later.plan_date)
    assert proposed not in plan.overdue() and len(plan.late()) > 0


def test_p16_remediation_form_workbook_plan_and_readiness(tmp_path: Path) -> None:
    client = TestClient(create_app())
    client.post("/user", data={"name": "Lena", "next": "/"})
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    page = client.get(url + "/contract/AR-DE-0026").text
    assert 'name="rp-30.2.a.2"' in page and "Provisions on this page" in page
    assert 'href="#pv-30_2_a_2"' in page and 'id="pv-30_2_a_2"' in page
    data = {"action": "save", "st-30.2.a.2": "missing", "rp-30.2.a.2": "negotiating",
            "ro-30.2.a.2": "Max", "rd-30.2.a.2": "2027-01-31",
            "st-30.1": "present", "rp-30.1": "agreed"}  # ignored: not a gap
    r = client.post(url + "/contract/AR-DE-0026", data=data, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(url + "/contract/AR-DE-0026").text
    assert "Remediation progress: In negotiation" in page
    plan_html = client.get(url + "/contracts/plan.html").text
    assert "In negotiation" in plan_html and "Max" in plan_html and "proposed" in plan_html
    assert "Progress:" in client.get(url + "/contracts").text
    audit = client.get(url + "/audit").text
    assert "remediation negotiating" in audit
    # the assessment workbook carries the fields and reads them back
    path = tmp_path / "a.xlsx"
    path.write_bytes(client.get(url + "/contracts/assessments.xlsx").content)
    book, problems = read_assessment_workbook(path)
    assert problems == []
    item = book.get("AR-DE-0026").item("30.2.a.2")  # type: ignore[union-attr]
    assert (item.remediation.value if item.remediation else None,  # type: ignore[union-attr]
            item.remediation_owner, item.remediation_due) == ("negotiating", "Max",
                                                              date(2027, 1, 31))
    assert book.get("AR-DE-0026").item("30.1").remediation is None  # type: ignore[union-attr]
    # plan workbook shows owner and progress
    plan_xlsx = tmp_path / "p.xlsx"
    plan_xlsx.write_bytes(client.get(url + "/contracts/plan.xlsx").content)
    ws = load_workbook(plan_xlsx).worksheets[0]
    header = [c.value for c in ws[1]]
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2) if row[0].value]
    pi, oi = header.index("Progress"), header.index("Owner")
    assert any(r[pi] == "In negotiation" and r[oi] == "Max" for r in rows)
    # bad workbook values are reported per row
    wb = load_workbook(path)
    sh = wb["Assessments"]
    hdr = [c.value for c in sh[1]]
    row = next(r for r in range(2, sh.max_row + 1)
               if sh.cell(row=r, column=1).value == "AR-DE-0026"
               and sh.cell(row=r, column=2).value == "30.2.a.2")
    sh.cell(row=row, column=hdr.index("remediation") + 1, value="soon")
    sh.cell(row=row, column=hdr.index("remediation_due") + 1, value="next year")
    wb.save(path)
    _, problems = read_assessment_workbook(path)
    assert any("remediation progress" in p for p in problems)
    assert any("remediation_due is not a date" in p for p in problems)


def test_p16_readiness_counts_progress_and_overdue() -> None:
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    html = client.get(url + "/readiness.html").text
    assert "high-priority gaps" in html and "not yet in negotiation" in html
    # the sample's Ledgerline item is past its agreed date (30 Sep 2026) from October 2026
    assert ("past the agreed target date" in html) is (date.today() > date(2026, 9, 30))


def test_p17_incident_shows_contractual_support() -> None:
    from dora_roi.contracts.analysis import incident_arrangements

    ws = sample_ws()
    inc = next(i for i in ws.incidents.ordered() if i.provider_codes)
    rows = incident_arrangements(ws.portfolio, inc.contract_refs, inc.provider_codes)
    assert rows and all(len(items) == 2 for _, items in rows)
    assert incident_arrangements(ws.portfolio, [], []) == []
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    page = client.get(f"{url}/incidents/{inc.id}").text
    assert "Contractual support (Art. 30)" in page and "30(2)(f)" in page
    assert "classified once" in page  # P-19 note


def test_p15_maintainer_marked_before_becoming_maintainer_is_kept() -> None:
    ws = sample_ws()
    maintainer = ws.register.maintainer.lei  # type: ignore[union-attr]
    ws.out_of_scope = {maintainer or "", SWISS_LIKE}
    leis = {e.lei for e in ws.dora_register().b_01_02}
    assert maintainer in leis and SWISS_LIKE not in leis
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    assert client.get(url + "/finma").status_code == 200


# =========================================================================== cycle 3


def _register_with_error_outside_scope() -> object:
    reg = generate_sample(inject_errors=False).source_register
    row = next(s for s in reg.b_02_02 if s.contract_ref == "AR-LU-0016")
    row.function_id = "F-UNKNOWN"  # XRF-004, only in the out-of-scope entity's rows
    return reg


def test_p20_package_is_validated_as_restricted(tmp_path: Path) -> None:
    reg = _register_with_error_outside_scope()
    src = tmp_path / "reg.xlsx"
    write_workbook(reg, src)  # type: ignore[arg-type]
    out = tmp_path / "pkg.zip"
    res = CliRunner().invoke(main, ["export", str(src), "-o", str(out), "--format",
                                    "xbrl-csv", "--strict"])
    assert res.exit_code != 0 and "refused" in res.output
    res = CliRunner().invoke(main, ["export", str(src), "-o", str(out), "--format",
                                    "xbrl-csv", "--strict", "--exclude-entity", SWISS_LIKE])
    assert res.exit_code == 0, res.output
    # workspace: full report keeps the error, the package report does not
    ws = Workspace("s", register_to_raw(reg))  # type: ignore[arg-type]
    assert [f.rule_id for f in ws.report.errors] == ["XRF-004"]
    assert ws.dora_report() is ws.report
    with ws.lock:
        ws.out_of_scope = {SWISS_LIKE}
        ws.programme_changed("scope", "B_01.02", "x")
    assert ws.dora_report().errors == [] and ws.dora_report() is ws.dora_report()
    ws.replace_programme(out_of_scope=set())
    assert ws.dora_report() is ws.report


def test_p20_import_findings_follow_the_scope() -> None:
    from dora_roi.scope import findings_in, restrict_to_scope

    ws = Workspace("s", register_to_raw(generate_sample().source_register))
    parse = ws._derive().parse_findings
    lu = [f for f in parse if f.record_key and SWISS_LIKE in f.record_key]
    assert lu, "the sample has an import finding in a Luxembourg row"
    restricted, _ = restrict_to_scope(ws.register, {SWISS_LIKE})
    kept = findings_in(parse, restricted)
    assert not set(map(id, lu)) & set(map(id, kept)) and len(kept) < len(parse)


def test_p20_export_page_shows_package_errors() -> None:
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "errors"},
                      follow_redirects=False).headers["location"]
    client.post(url + "/scope", data={"out": [SWISS_LIKE]})
    page = client.get(url + "/export").text
    assert "Validation of the package itself:" in page


def test_p21_readiness_register_light_is_the_submission() -> None:
    from dora_roi.readiness import Rag
    from dora_roi.web.programme_routes import workspace_readiness

    ws = Workspace("s", register_to_raw(_register_with_error_outside_scope()))  # type: ignore
    pillar = next(p for p in workspace_readiness(ws, "en").pillars if p.key == "register")
    assert pillar.rag is Rag.AMBER and "1 error(s)" in pillar.lines[1]
    with ws.lock:
        ws.out_of_scope = {SWISS_LIKE}
        ws.programme_changed("scope", "B_01.02", "x")
    pillar = next(p for p in workspace_readiness(ws, "en").pillars if p.key == "register")
    assert pillar.rag is Rag.GREEN and "0 error(s)" in pillar.lines[1]
    assert any("Submission view" in line for line in pillar.lines)
    de = next(p for p in workspace_readiness(ws, "de").pillars if p.key == "register")
    assert any("Sicht der Meldung" in line for line in de.lines)


def test_p20_acceptances_apply_to_the_package() -> None:
    from dora_roi.validation import Severity

    ws = Workspace("s", register_to_raw(generate_sample().source_register))
    warning = next(f for f in ws.report.findings if f.severity is Severity.WARNING
                   and f.rule_id == "BUS-016")  # an Austrian function: stays in scope
    ws.accept(warning, "known, documented")
    with ws.lock:
        ws.out_of_scope = {SWISS_LIKE}
        ws.programme_changed("scope", "B_01.02", "x")
    package = ws.dora_report()
    assert package is not ws.report
    assert any(f.rule_id == warning.rule_id and f.accepted_reason for f in package.accepted)
    assert all(f.message != warning.message or f.record_key != warning.record_key
               for f in package.findings)


def test_p26_readiness_cli_scope(tmp_path: Path) -> None:
    import json

    src = tmp_path / "reg.xlsx"
    write_workbook(_register_with_error_outside_scope(), src)  # type: ignore[arg-type]
    out, js = tmp_path / "r.html", tmp_path / "r.json"
    res = CliRunner().invoke(main, ["readiness", str(src), "-o", str(out), "--json", str(js),
                                    "--exclude-entity", SWISS_LIKE])
    assert res.exit_code == 0, res.output
    register = next(p for p in json.loads(js.read_text())["pillars"] if p["key"] == "register")
    assert register["status"] == "green"
    assert any("Submission view" in line for line in register["details"])
    res = CliRunner().invoke(main, ["readiness", str(src), "-o", str(out), "--exclude-entity",
                                    "3912RO6DCAXX71K9W972"])
    assert res.exit_code != 0 and "maintaining" in res.output


# =========================================================================== after merge


def test_p29_programme_exports_are_audited_and_signed() -> None:
    client = TestClient(create_app())
    client.post("/user", data={"name": "Lena", "next": "/"})
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    assert "Lena" in client.get(url + "/readiness.html").text
    assert "Lena" in client.get(url + "/contracts/plan.html").text
    assert "Lena" in client.get(url + "/incidents/summary.html").text
    for path in ("/contracts/plan.xlsx", "/contracts/assessments.json",
                 "/contracts/assessments.xlsx", "/incidents/summary.json",
                 "/incidents/log.json"):
        assert client.get(url + path).status_code == 200
    audit = client.get(url + "/download/audit.csv").text
    for label in ("DORA readiness report (HTML)", "Art. 30 remediation plan (HTML)",
                  "Art. 30 remediation plan (Excel)", "Art. 30 assessments (JSON)",
                  "Art. 30 assessments (Excel)", "Incident summary (HTML)",
                  "Incident summary (JSON)", "Incident log (JSON)"):
        assert label in audit, label
    # the xBRL package export records the submission view
    client.post(url + "/scope", data={"out": [SWISS_LIKE]})
    client.get(url + "/download/xbrl")
    audit = client.get(url + "/download/audit.csv").text
    assert "xBRL-CSV package without 1 entit(y/ies) outside the DORA scope" in audit


def test_p30_programme_pdfs_respect_the_pdf_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from dora_roi.reporting.pdf import PdfBusyError
    from dora_roi.web import programme_routes

    def busy(html: str, **_: object) -> bytes:
        raise PdfBusyError("the server is busy rendering other PDFs; please try again")

    monkeypatch.setattr(programme_routes, "html_to_pdf", busy)
    monkeypatch.setattr(programme_routes, "pdf_available", lambda: True)
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"},
                      follow_redirects=False).headers["location"]
    for path in ("/readiness.pdf", "/contracts/plan.pdf", "/incidents/summary.pdf"):
        r = client.get(url + path)
        assert r.status_code == 503 and r.headers["retry-after"] == "10", path
