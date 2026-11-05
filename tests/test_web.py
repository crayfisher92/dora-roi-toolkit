"""Route-level tests of the web workbench (FastAPI TestClient)."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dora_roi.io.csv_folder import register_to_csv_texts
from dora_roi.io.excel import write_workbook
from dora_roi.sample.inventory_sample import write_sample_inventory
from dora_roi.web.app import create_app
from dora_roi.web.i18n import MESSAGES, pick_language, translator

from conftest import ENTITY, build_valid_register


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(capacity=6))


def _new(client: TestClient, variant: str = "dirty") -> str:
    r = client.post("/sample", data={"variant": variant}, follow_redirects=False)
    assert r.status_code == 303
    return str(r.headers["location"])


def test_i18n_catalogues_match() -> None:
    assert set(MESSAGES["en"]) == set(MESSAGES["de"])
    t = translator("de")
    assert t("step.fix") == "Korrigieren" and t("ws.next.fix", n=3).startswith("3")
    assert translator("fr")("step.fix") == "Fix"
    assert t("does.not.exist") == "does.not.exist"
    assert pick_language(None, None, "de-CH,de;q=0.9,en;q=0.8") == "de"
    assert pick_language("en", "de", "de") == "en"
    assert pick_language(None, "de", None) == "de"
    assert pick_language(None, None, "fr") == "en"


def test_home_language_and_static(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200 and 'lang="en"' in r.text and "Skip to content" in r.text
    r = client.get("/?lang=de")
    assert 'lang="de"' in r.text and "Arbeitsbereich" in r.text
    assert r.cookies.get("lang") == "de"
    assert 'lang="de"' in client.get("/").text  # cookie remembered
    fresh = TestClient(create_app())
    assert 'lang="de"' in fresh.get("/", headers={"accept-language": "de"}).text
    assert "fetch(" in client.get("/static/app.js").text
    assert ".stepper" in client.get("/static/app.css").text
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/template.xlsx").content[:2] == b"PK"


def test_import_roi_workbook_and_errors(client: TestClient, tmp_path: Path) -> None:
    path = write_workbook(build_valid_register(), tmp_path / "reg.xlsx")
    r = client.post("/import", files={"file": ("reg.xlsx", path.read_bytes())},
                    follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"])
    assert "Ready for submission" in page.text and "100" in page.text
    r = client.post("/import", files={"file": ("notes.txt", b"x")})
    assert r.status_code == 400 and "Unsupported file type" in r.text
    r = client.post("/import", files={"file": ("bad.zip", b"PK-not-a-zip")})
    assert r.status_code == 400 and "Could not read" in r.text
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in register_to_csv_texts(build_valid_register()).items():
            zf.writestr(name, text)
    r = client.post("/import", files={"file": ("csv.zip", buf.getvalue())},
                    follow_redirects=False)
    assert r.status_code == 303


def test_upload_too_large(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import dora_roi.web.app as webapp

    monkeypatch.setattr(webapp, "MAX_UPLOAD_BYTES", 10)
    r = client.post("/import", files={"file": ("big.xlsx", b"x" * 50)})
    assert r.status_code == 400 and "too large" in r.text


def test_workspace_pages_render(client: TestClient) -> None:
    url = _new(client)
    for suffix in ("", "/fix", "/fix?severity=warning", "/fix?template=B_02.02&rule=FLD-005",
                   "/register/B_05.02?q=nimbus", "/register/B_02.02?issues=1&page=9",
                   "/register/B_02.02/4", "/analyse", "/analyse?color=region&critical=1",
                   "/analyse?isolated=1&color=bogus", "/export", "/compare", "/versions",
                   "/compare?version=1"):
        r = client.get(url + suffix)
        assert r.status_code == 200, suffix
        assert 'aria-current="step"' in r.text, suffix
    assert client.get(url + "/register", follow_redirects=False).status_code == 303
    assert client.get(url + "/register/B_99.99").status_code == 404
    assert client.get(url + "/register/B_02.02/9999").status_code == 404
    assert client.get(url + "/compare?version=999").status_code == 404
    assert client.get("/w/nope").status_code == 404
    assert client.get("/w/nope", headers={"accept": "application/json"}).json()["detail"]
    assert client.get("/api/w/nope").status_code == 404
    summary = client.get("/api" + url).json()
    assert summary["readiness"] == "not_ready" and summary["counts"]["error"] == 27


def test_fix_flow_json_and_form(client: TestClient) -> None:
    url = _new(client)
    page = client.get(url + "/fix?template=B_02.02&severity=error").text
    assert "Why it matters" in page and "Use suggestion" in page and "ITS Annex II" in page
    m = re.search(r'name="row" value="(\d+)">\s*<input type="hidden" name="column" '
                  r'value="c0120"', page)
    assert m, "UK finding with inline editor expected"
    row = m.group(1)
    data = {"template": "B_02.02", "row": row, "column": "c0120", "value": "GB"}
    r = client.post(url + "/cell", data=data, headers={"accept": "application/json"})
    body = r.json()
    assert body["changed"] and body["resolved"] and body["counts"]["error"] == 26
    r = client.post(url + "/cell", data=data, headers={"accept": "application/json"})
    assert r.json()["changed"] is False and r.json()["message"] == "Value unchanged."
    r = client.post(url + "/cell", data={**data, "value": "XX", "next": "//evil.example"},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == url + "/fix"
    r = client.post(url + "/cell", data={**data, "row": "abc"})
    assert r.status_code == 400
    r = client.post(url + "/cell", data={**data, "column": "c9999"})
    assert r.status_code == 400


def test_bulk_fix(client: TestClient) -> None:
    url = client.post("/map", data={"use_sample": "1"}, follow_redirects=False)
    wiz = url.headers["location"]
    r = client.post(wiz + "/entity", data={"lei": ENTITY, "name": "Bank", "country": "DE",
                                           "reporting_date": "2025-12-31", "currency": "EUR"},
                    follow_redirects=False)
    assert r.status_code == 303
    ws_url = client.post(wiz + "/import", follow_redirects=False).headers["location"]
    page = client.get(ws_url + "/fix?template=B_02.02").text
    assert "Fix repeated errors at once" in page
    errors_before = client.get("/api" + ws_url).json()["counts"]["error"]
    m = re.search(r'name="column" value="(c\d+)">\s*<input type="hidden" name="old" value="">'
                  r'<input type="hidden" name="rows" value="([\d,]+)"', page)
    assert m
    r = client.post(ws_url + "/bulk", data={"template": "B_02.02", "column": m.group(1),
                                            "old": "", "rows": m.group(2), "new": "90",
                                            "next": ws_url + "/fix"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api" + ws_url).json()["counts"]["error"] < errors_before
    r = client.post(ws_url + "/bulk", data={"template": "B_99", "column": "c0010", "old": "",
                                            "new": "x"})
    assert r.status_code == 400


def test_register_row_edit_add_delete(client: TestClient) -> None:
    url = _new(client, "clean")
    r = client.post(url + "/register/B_06.01", follow_redirects=False)
    row_url = r.headers["location"]
    assert client.get(row_url).status_code == 200
    r = client.post(row_url, data={"c0010": "F-NEW", "c0030": "New function",
                                   "c0050": "NOT_CRITICAL"}, follow_redirects=False)
    assert r.status_code == 303 and "saved=1" in r.headers["location"]
    page = client.get(r.headers["location"]).text
    assert "F-NEW" in page and "Saved." in page and "FLD-001" in page
    r = client.post(row_url, data={"delete": "1"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.get(row_url).status_code == 404
    assert client.post(row_url, data={"delete": "1"}).status_code == 404
    assert client.post(row_url, data={"c0010": "x"}).status_code == 404
    assert client.post(url + "/register/B_99.99").status_code == 404


def test_provider_page(client: TestClient) -> None:
    url = _new(client, "clean")
    page = client.get(url + "/register/B_05.01").text
    codes = re.findall(r"/provider/([A-Z0-9.\-]+)\"", page)
    assert codes
    nimbus = None
    for code in dict.fromkeys(codes):
        p = client.get(url + "/provider/" + code)
        assert p.status_code == 200
        if "Nimbus Cloud Services EMEA Ltd" in p.text:
            nimbus = p.text
    assert nimbus and "Risk flags" in nimbus and "Subcontractor in" in nimbus
    assert "dep-graph" in nimbus
    assert client.get(url + "/provider/UNKNOWN").status_code == 404


def test_downloads(client: TestClient) -> None:
    url = _new(client)
    assert client.get(url + "/download/xlsx").content[:2] == b"PK"
    names = zipfile.ZipFile(io.BytesIO(client.get(url + "/download/csv").content)).namelist()
    assert "b_02.02.csv" in names
    names = zipfile.ZipFile(io.BytesIO(client.get(url + "/download/xbrl").content)).namelist()
    assert any(n.endswith("reports/report.json") for n in names)
    assert "<!doctype html>" in client.get(url + "/download/validation.html").text
    assert client.get(url + "/download/validation.md").text.startswith("# DORA")
    assert client.get(url + "/download/validation.json").json()["passed"] is False
    assert "Key messages" in client.get(url + "/download/executive.html").text
    assert "totals" in client.get(url + "/download/analysis.json").json()
    assert client.get(url + "/download/nope").status_code == 404


def test_compare_pair_and_upload(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/sample", data={"variant": "pair"}, follow_redirects=False)
    page = client.get(r.headers["location"]).text
    assert "Legacy Mainframe Services GmbH" in page and "Alpenrand 2024" in page
    url = r.headers["location"].split("/compare")[0]
    path = write_workbook(build_valid_register(), tmp_path / "old.xlsx")
    r = client.post(url + "/compare", files={"file": ("old.xlsx", path.read_bytes())},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "old.xlsx" in client.get(r.headers["location"]).text
    r = client.post(url + "/compare", files={"file": ("x.txt", b"x")})
    assert r.status_code == 400
    r = client.post(url + "/compare", files={"file": ("x.zip", b"garbage")})
    assert r.status_code == 400


def test_wizard_full_flow_and_validation(client: TestClient, tmp_path: Path) -> None:
    assert "Upload" in client.get("/map").text
    r = client.post("/map", data={})
    assert r.status_code == 400
    r = client.post("/map", files={"file": ("x.pdf", b"x")})
    assert r.status_code == 400 and "Unsupported" in r.text
    r = client.post("/map", files={"file": ("x.xlsx", b"broken")})
    assert r.status_code == 400 and "Could not read" in r.text
    inv = write_sample_inventory(tmp_path / "inv.xlsx")
    r = client.post("/map", files={"file": ("inv.xlsx", inv.read_bytes())},
                    follow_redirects=False)
    wiz = r.headers["location"]
    page = client.get(wiz).text
    assert "Vertragsnummer" in page and "confident match" in page
    assert client.get(wiz + "/preview", follow_redirects=False).status_code == 303
    assert client.post(wiz + "/import", follow_redirects=False).status_code == 303
    form = {f"col{i}": key for i, key in enumerate(
        ["contract_ref", "provider_name", "provider_lei", "provider_country", "service",
         "function_name", "critical", "start_date", "end_date", "annual_cost", "currency",
         "data_location", "exit_plan", "substitutability", "contract_ref"])}
    assert client.post(wiz, data=form, follow_redirects=False).status_code == 303
    assert "LEI of your entity" in client.get(wiz + "/entity").text
    r = client.post(wiz + "/entity", data={"lei": "BAD", "name": "", "country": "DE",
                                           "reporting_date": "nope"})
    assert r.status_code == 400 and 'aria-invalid="true"' in r.text
    r = client.post(wiz + "/entity", data={"lei": ENTITY, "name": "Alpenrand",
                                           "country": "DE", "reporting_date": "2025-12-31",
                                           "entity_type": "CREDIT_INSTITUTION",
                                           "currency": "EUR"}, follow_redirects=False)
    assert r.headers["location"].endswith("/preview")
    page = client.get(wiz + "/preview").text
    assert re.search(r"\d{4}-\d{2}-\d{2}", page) and "<s>" in page
    ws_url = client.post(wiz + "/import", follow_redirects=False).headers["location"]
    page = client.get(ws_url).text
    assert "Import summary" in page and "inventory rows imported" in page
    assert client.get("/map/unknown").status_code == 404


def test_store_eviction() -> None:
    c = TestClient(create_app(capacity=2))
    urls = [_new(c, "clean") for _ in range(3)]
    assert c.get(urls[0]).status_code == 404
    assert c.get(urls[2]).status_code == 200


def test_german_workspace(client: TestClient) -> None:
    url = _new(client)
    page = client.get(url + "/fix?template=B_02.02&lang=de").text
    assert "Befunde beheben" in page and "Warum das wichtig ist" in page
    assert "Großbritannien ist GB" in page or "Ländercode" in page
