"""Route-level tests of the DORA programme screens (Art. 30 contracts, incidents, FINMA,
dashboard) in the web workbench."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from dora_roi.contracts import AssessmentBook, ContractAssessment, write_assessment_workbook
from dora_roi.io.excel import write_workbook
from dora_roi.sample.contract_docs import SAMPLE_CONTRACT_TEXT, docx_bytes
from dora_roi.web.app import create_app
from dora_roi.web.context import download, form_text

from conftest import build_valid_register


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(capacity=6))


def _sample(client: TestClient, variant: str = "dirty") -> str:
    r = client.post("/sample", data={"variant": variant}, follow_redirects=False)
    assert r.status_code == 303
    return str(r.headers["location"])


def _upload(client: TestClient, tmp_path: Path) -> str:
    path = write_workbook(build_valid_register(), tmp_path / "reg.xlsx")
    r = client.post("/import", files={"file": ("reg.xlsx", path.read_bytes())},
                    follow_redirects=False)
    return str(r.headers["location"])


# =========================================================================== contracts


def test_contracts_portfolio_filters_and_downloads(client: TestClient) -> None:
    url = _sample(client)
    page = client.get(url + "/contracts")
    assert page.status_code == 200 and "DORA Art. 30 contract gap analysis" in page.text
    assert "Nimbus Cloud Services EMEA Ltd" in page.text and 'aria-current="page"' in page.text
    gaps = client.get(url + "/contracts?status=gaps&critical=1&q=helix")
    assert "AR-DE-0022" in gaps.text and "AR-DE-0026" not in gaps.text
    assert "AR-DE-0030" not in client.get(url + "/contracts?status=bogus&q=zzz").text
    de = client.get(url + "/contracts?lang=de")
    assert "Lückenanalyse" in de.text and "Maßnahmenplan" in de.text
    assert "Maßnahmenplan" in client.get(url + "/contracts/plan.html").text  # cookie
    client.cookies.clear()
    plan = client.get(url + "/contracts/plan.html")
    assert plan.status_code == 200 and "Contract remediation plan" in plan.text
    xlsx = client.get(url + "/contracts/plan.xlsx")
    assert xlsx.content[:2] == b"PK" and "remediation-plan.xlsx" in xlsx.headers[
        "content-disposition"]
    assert load_workbook(io.BytesIO(xlsx.content)).sheetnames[0] == "Remediation plan"
    js = client.get(url + "/contracts/assessments.json")
    assert AssessmentBook.from_json(js.content).get("AR-DE-0057") is not None
    wb = client.get(url + "/contracts/assessments.xlsx")
    assert load_workbook(io.BytesIO(wb.content)).sheetnames[0] == "Assessments"
    chk = client.get(url + "/contracts/checklist")
    assert "30(3)(e)(i)" in chk.text and "DORA Art. 28(7)" in chk.text


def test_assessment_save_history_and_register_link(client: TestClient, tmp_path: Path) -> None:
    url = _upload(client, tmp_path)
    page = client.get(url + "/contract/C-001")
    assert page.status_code == 200 and "Art. 30(2) + 30(3)" in page.text
    assert "SaaS Vendor GmbH" in page.text and "Not assessed" in page.text
    form = {"action": "save", "assessor": "Lena", "assessed_on": "2025-11-04",
            "document": "MSA.pdf", "notes": "first pass", "st-30.3.d": "missing",
            "cl-30.3.d": "", "ev-30.3.d": "No TLPT clause", "st-30.1": "present",
            "cl-30.1": "1", "ev-30.1": "", "sg-30.1": "present", "ev-30.2.c": "note only"}
    r = client.post(url + "/contract/C-001", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("?saved=1")
    page = client.get(r.headers["location"])
    assert "Assessment saved" in page.text and "Assessment created" in page.text
    assert "Lena" in page.text
    reg = client.get(url + "/register/B_02.01")
    assert "Art. 30" in reg.text and "/contract/C-001" in reg.text and "Gaps" in reg.text
    row = client.get(url + "/register/B_02.01/4")
    assert "DORA Art. 30 contract assessment" in row.text and "Open assessment" in row.text
    row = client.get(url + "/register/B_02.02/4")
    assert "DORA Art. 30 contract assessment" in row.text
    assert "Art. 30 contract compliance" not in client.get(url + "/register/B_05.01/4").text
    form["st-30.3.d"] = "present"
    client.post(url + "/contract/C-001", data=form)
    page = client.get(url + "/contract/C-001")
    assert "30.3.d: missing → present" in page.text
    bad = dict(form, assessed_on="31.12.2025")
    r = client.post(url + "/contract/C-001", data=bad)
    assert r.status_code == 400 and "could not be saved" in r.text
    r = client.post(url + "/contract/C-001", data={"action": "delete"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get(url + "/contracts/assessments.json").json()["assessments"] == {}
    assert client.get(url + "/contract/NOPE").status_code == 404
    assert client.post(url + "/contract/NOPE", data={"action": "save"}).status_code == 404


def test_suggestions_from_uploaded_documents(client: TestClient, tmp_path: Path) -> None:
    url = _upload(client, tmp_path)
    files = {"file": ("contract.docx", docx_bytes(SAMPLE_CONTRACT_TEXT))}
    r = client.post(url + "/contract/C-001", data={"action": "suggest"}, files=files)
    assert r.status_code == 200 and "Suggestions – not saved yet" in r.text
    assert "Suggestion: not found" in r.text and 'name="sg-30.3.d" value="missing"' in r.text
    assert "[Suggestion – review]" in r.text and "contract.docx" in r.text
    # nothing is saved until the form is submitted
    assert client.get(url + "/contracts/assessments.json").json()["assessments"] == {}
    r = client.post(url + "/contract/C-001?lang=de", data={"action": "suggest"},
                    files={"file": ("v.txt", SAMPLE_CONTRACT_TEXT.encode())})
    assert "[Vorschlag – prüfen]" in r.text
    client.cookies.clear()
    r = client.post(url + "/contract/C-001", data={"action": "suggest"},
                    files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 400 and "Unsupported document type" in r.text
    r = client.post(url + "/contract/C-001", data={"action": "suggest"},
                    files={"file": ("broken.docx", b"PK-no")})
    assert r.status_code == 400 and "Could not read" in r.text
    r = client.post(url + "/contract/C-001", data={"action": "suggest"})
    assert r.status_code == 400 and "Choose a contract document" in r.text


def test_sample_contract_button_and_inheritance(client: TestClient) -> None:
    url = _sample(client, "clean")
    page = client.get(url + "/contract/AR-DE-0057")
    assert "Use the sample contract" in page.text
    r = client.post(url + "/contract/AR-DE-0057", data={"action": "sample"})
    assert r.status_code == 200 and "Mobilio-Digital-Banking" in r.text
    co = client.get(url + "/contract/CO-LU-0002")
    assert "inherited from MSA-DE-0001" in co.text and 'name="inherit_shown"' in co.text
    assert "Call-off under" in co.text
    r = client.post(url + "/contract/CO-LU-0002", data={"action": "save", "inherit_shown": "1"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "Not assessed" in client.get(url + "/contracts?q=CO-LU-0002").text
    msa = client.get(url + "/contract/MSA-DE-0001")
    assert "call-off(s) rely on it" in msa.text
    hr = client.get(url + "/contract/AR-DE-0064")
    assert "Art. 30(3) does not apply" in hr.text
    prov = client.get(url + "/provider/5299XGE5RGK9SNVGG353")
    assert "Art. 30 contract compliance" in prov.text and "MSA-DE-0001" in prov.text


def test_import_assessments(client: TestClient, tmp_path: Path) -> None:
    url = _upload(client, tmp_path)
    book = AssessmentBook()
    a = ContractAssessment(contract_ref="C-001")
    a.set("30.3.d", "missing")
    book.save(a)
    book.save(ContractAssessment(contract_ref="GONE"))
    r = client.post(url + "/contracts/import",
                    files={"file": ("a.json", book.to_json().encode())}, follow_redirects=False)
    assert r.status_code == 303 and "imported=2" in r.headers["location"]
    page = client.get(r.headers["location"])
    assert "2 assessment(s) imported" in page.text and "not in the register" in page.text
    assert client.get(url + "/contract/GONE").status_code == 200
    path = write_assessment_workbook(book, tmp_path / "a.xlsx")
    r = client.post(url + "/contracts/import",
                    files={"file": ("a.xlsx", path.read_bytes())}, follow_redirects=False)
    assert r.status_code == 303
    r = client.post(url + "/contracts/import", files={"file": ("a.json", b"{}")})
    assert r.status_code == 400 and "schema" in r.text
    r = client.post(url + "/contracts/import", files={"file": ("a.txt", b"x")})
    assert r.status_code == 400 and "Unsupported" in r.text
    r = client.post(url + "/contracts/import", files={"file": ("a.xlsx", b"not excel")})
    assert r.status_code == 400


def test_web_context_helpers() -> None:
    r = download(b"x", "plan ü/../x.xlsx", "text/plain")
    assert r.headers["content-disposition"] == 'attachment; filename="plan___.._x.xlsx"'
    assert form_text({"a": "  hi  ", "b": object()}, "a") == "hi"
    assert form_text({"b": object()}, "b") == "" and form_text({}, "c") == ""


# =========================================================================== incidents


def test_incident_log_page_and_exports(client: TestClient) -> None:
    url = _sample(client)
    page = client.get(url + "/incidents")
    assert page.status_code == 200 and "Major ICT-related incident classification" in page.text
    assert "kronos-certificate-rotation" in page.text and "time class=\"countdown" in page.text
    assert "Nimbus EMEA region outage" in page.text
    html = client.get(url + "/incidents/summary.html")
    assert html.status_code == 200 and "ICT-related incident summary" in html.text
    data = client.get(url + "/incidents/summary.json").json()
    assert data["counts"]["major"] == 1 and data["counts"]["recurring_major"] == 1
    log = client.get(url + "/incidents/log.json")
    assert "incident-log.json" in log.headers["content-disposition"]
    de = client.get(url + "/incidents?lang=de")
    assert "Vorfallverzeichnis" in de.text and "Wiederkehrende Vorfälle" in de.text
    client.cookies.clear()
    r = client.post(url + "/incidents/settings", data={"timezone": "Europe/Zurich"},
                    follow_redirects=False)
    assert r.status_code == 303 and "Times in Europe/Zurich" in client.get(
        url + "/incidents").text
    client.post(url + "/incidents/settings", data={"timezone": "Mars/Base"})
    assert "Times in Europe/Zurich" in client.get(url + "/incidents").text
    prov = client.get(url + "/provider/5299XGE5RGK9SNVGG353")
    assert "Incidents involving this provider" in prov.text


def test_incident_create_classify_and_report(client: TestClient, tmp_path: Path) -> None:
    url = _upload(client, tmp_path)
    form = client.get(url + "/incidents/new")
    assert form.status_code == 200 and "Classification questionnaire" in form.text
    assert 'name="a-critical_services"' in form.text and "SaaS Vendor GmbH" in form.text
    data = {"title": "Payment SaaS down", "detected_at": "2025-12-01T09:00",
            "occurred_at": "2025-12-01T08:45", "a-critical_services": "yes",
            "a-malicious_access": "no", "a-downtime_hours": "3,5", "ms": ["DE", "AT", "XX"],
            "provider": "", "contract": "C-001", "entity": [], "status": "open",
            "root_cause": "third_party_failure", "a-economic_eur": "150'000",
            "a-clients_affected": "1,200"}
    r = client.post(url + "/incidents/new", data=data, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"].split("?")[0]
    iid = loc.rsplit("/", 1)[1]
    page = client.get(loc)
    assert "Major" in page.text and "Initial notification" in page.text
    assert "costs and losses" in page.text and "Payments" in page.text
    assert "The linked arrangements support critical or important functions" in page.text
    assert "— → major" in page.text
    js = client.get(url + "/incidents/summary.json").json()
    inc = js["incidents"][0]
    assert inc["classification"]["outcome"] == "major" and inc["classified_at"]
    # record the initial notification, resolve, close, reopen
    r = client.post(loc, data={"action": "report", "kind": "initial",
                               "submitted_at": "2025-12-01T11:00"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Initial notification submitted" in client.get(loc).text
    assert client.post(loc, data={"action": "report", "kind": "bogus"}).status_code == 400
    assert client.post(loc, data={"action": "report", "kind": "final",
                                  "submitted_at": "yesterday"}).status_code == 400
    for action, text in (("resolve", "Resolved"), ("close", "Closed"), ("reopen", "Reopened")):
        client.post(loc, data={"action": action})
        assert text in client.get(loc).text
    # edit: answers change the classification and are recorded
    data.update({"a-critical_services": "no"})
    client.post(loc, data=data)
    page = client.get(loc)
    assert "major → not_major" in page.text and "Not major" in page.text
    bad = dict(data, **{"a-downtime_hours": "-1"})
    r = client.post(loc, data=bad)
    assert r.status_code == 400 and "Please check" in r.text
    assert client.post(loc, data={"action": "delete"}, follow_redirects=False).status_code == 303
    assert client.get(loc).status_code == 404
    assert client.post(loc, data={"action": "save"}).status_code == 404
    assert iid.startswith("INC-")


@pytest.mark.parametrize(("field", "value"), [
    ("title", ""), ("detected_at", ""), ("detected_at", "01.12.2025"),
    ("a-clients_total", "many"), ("status", "bogus"),
])
def test_incident_form_validation(client: TestClient, tmp_path: Path, field: str,
                                  value: str) -> None:
    url = _upload(client, tmp_path)
    data = {"title": "X", "detected_at": "2025-12-01T09:00", field: value}
    r = client.post(url + "/incidents/new", data=data)
    assert r.status_code == 400 and "Please check" in r.text


def test_incident_import(client: TestClient, tmp_path: Path) -> None:
    url = _upload(client, tmp_path)
    from dora_roi.incidents import Incident, IncidentLog

    log = IncidentLog()
    log.save(Incident(id="INC-2025-001", title="Imported", detected_at="2025-11-01T10:00:00Z"),
             "created")
    r = client.post(url + "/incidents/import", files={"file": ("l.json", log.to_json().encode())},
                    follow_redirects=False)
    assert r.status_code == 303 and "imported=1" in r.headers["location"]
    assert "1 incident(s) imported" in client.get(r.headers["location"]).text
    r = client.post(url + "/incidents/import", files={"file": ("l.json", b"{}")})
    assert r.status_code == 400
    r = client.post(url + "/incidents/import", files={"file": ("l.txt", b"{}")})
    assert r.status_code == 400 and "Unsupported" in r.text


# =========================================================================== FINMA


def test_finma_page(client: TestClient, tmp_path: Path) -> None:
    url = _sample(client)
    page = client.get(url + "/finma")
    assert page.status_code == 200 and "One dataset for DORA and FINMA" in page.text
    assert "FIN-OS-11" in page.text and "Helix Core Banking AG" in page.text
    assert "No Swiss entity in B_01.02" in page.text and "56%" in page.text
    de = client.get(url + "/finma?lang=de")
    assert "Ein Datenbestand für DORA und FINMA" in de.text
    client.cookies.clear()
    bare = _upload(client, tmp_path)
    assert "not assessed yet" in client.get(bare + "/finma").text


# =========================================================================== readiness


def test_dashboard_report_and_overview(client: TestClient) -> None:
    url = _sample(client)
    page = client.get(url + "/dashboard")
    assert page.status_code == 200 and "DORA readiness dashboard" in page.text
    assert "Action required" in page.text and "kronos-certificate-rotation" in page.text
    assert f'href="{url}/contracts?status=gaps&amp;critical=1"' in page.text
    report = client.get(url + "/readiness.html")
    assert report.status_code == 200 and "DORA readiness report" in report.text
    overview = client.get(url)
    assert "DORA readiness dashboard" in overview.text and f"{url}/dashboard" in overview.text
    de = client.get(url + "/dashboard?lang=de")
    assert "DORA-Reifegrad im Überblick" in de.text
