"""Regression tests for the BACKLOG cycle-1 findings (security, performance, TPR features)."""

from __future__ import annotations

import csv
import io
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from dora_roi.analytics import analyse
from dora_roi.analytics.impact import failure_impact
from dora_roi.audit import audit_csv
from dora_roi.audit import csv_safe as _csv_safe
from dora_roi.diff import diff_registers
from dora_roi.io.excel import write_workbook
from dora_roi.io.limits import InputTooLargeError, check_archive
from dora_roi.io.loader import load
from dora_roi.sample import generate_previous_year, generate_sample, register_to_raw
from dora_roi.validation import Severity
from dora_roi.web.app import clean_user, create_app
from dora_roi.web.security import APP_CSP, REPORT_CSP, safe_next
from dora_roi.workspace import EditError, Workspace

from conftest import build_valid_register


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(capacity=4))


def _ws_url(client: TestClient, variant: str = "dirty") -> str:
    r = client.post("/sample", data={"variant": variant}, follow_redirects=False)
    return str(r.headers["location"]).split("/compare")[0]


# ------------------------------------------------------------------ B-01 formula injection


def test_excel_export_never_writes_formulas(tmp_path: Path) -> None:
    reg = build_valid_register()
    reg.b_05_01[0].legal_name = '=HYPERLINK("http://evil.example","x")'
    reg.b_05_01[1].legal_name = "+SUM(A1)"
    path = write_workbook(reg, tmp_path / "x.xlsx")
    ws = load_workbook(path)["B_05.01"]
    for row in (4, 5):
        cell = ws.cell(row=row, column=5)
        assert cell.data_type == "s", cell.value
        assert cell.quotePrefix
    assert load(path).register.b_05_01[0].legal_name == '=HYPERLINK("http://evil.example","x")'


def test_csv_safe() -> None:
    assert _csv_safe("=1+1") == "'=1+1" and _csv_safe("@x") == "'@x"
    assert _csv_safe("ok") == "ok" and _csv_safe(None) == ""


# ------------------------------------------------------------------ B-02 size limits


def test_row_limit_rejects_huge_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROI_MAX_ROWS_PER_TABLE", "100")
    zpath = tmp_path / "big.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("b_02.01.csv", "c0010\n" + "A\n" * 500)
    started = time.monotonic()
    with pytest.raises(InputTooLargeError, match="more than 100 rows"):
        load(zpath)
    assert time.monotonic() - started < 5


def test_archive_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROI_MAX_UNCOMPRESSED_MB", "1")
    zpath = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("b_02.01.csv", "0" * (3 * 1024 * 1024))
    with pytest.raises(InputTooLargeError, match="expands to 3 MB"):
        check_archive(zpath)
    plain = tmp_path / "plain.txt"
    plain.write_text("x")
    check_archive(plain)  # not a zip: no-op


def test_web_reports_size_errors(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROI_MAX_ROWS_PER_TABLE", "10")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("b_02.01.csv", "c0010\n" + "A\n" * 50)
    r = client.post("/import", files={"file": ("big.zip", buf.getvalue())})
    assert r.status_code == 400 and "more than 10 rows" in r.text


# ------------------------------------------------------------------ B-04/05/06 web security


@pytest.mark.parametrize(("target", "ok"), [
    ("/w/abc/fix", True), ("//evil.example", False), ("/\\evil.example", False),
    ("https://evil.example", False), ("/ok\r\nSet-Cookie: x", False), ("", False),
    ("relative", False), ("/%2F%2Fevil", True)])
def test_safe_next(target: str, ok: bool) -> None:
    assert (safe_next(target, "/default") == target) is ok


def test_cross_site_posts_are_rejected(client: TestClient) -> None:
    r = client.post("/sample", data={"variant": "clean"},
                    headers={"origin": "http://evil.example"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/sample", data={"variant": "clean"},
                    headers={"referer": "http://evil.example/page"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/sample", data={"variant": "clean"},
                    headers={"sec-fetch-site": "cross-site"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/sample", data={"variant": "clean"},
                    headers={"origin": "http://testserver"}, follow_redirects=False)
    assert r.status_code == 303
    r = client.post("/sample", data={"variant": "clean"},
                    headers={"sec-fetch-site": "same-origin", "origin": "null"},
                    follow_redirects=False)
    assert r.status_code == 303
    r = client.post("/sample", data={"variant": "clean"},
                    headers={"sec-fetch-site": "same-site"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/sample", data={"variant": "clean"}, headers={"origin": "null"},
                    follow_redirects=False)
    assert r.status_code == 403


def test_security_headers(client: TestClient) -> None:
    r = client.get("/")
    assert r.headers["content-security-policy"] == APP_CSP
    assert "script-src 'self';" in APP_CSP and "frame-ancestors 'none'" in APP_CSP
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert "<script>" not in r.text  # no inline script on app pages
    url = _ws_url(client)
    assert client.get(url).headers["cache-control"] == "no-store"
    rep = client.get(url + "/download/executive.html")
    assert rep.headers["content-security-policy"] == REPORT_CSP


def test_workspace_ids_are_unguessable(client: TestClient) -> None:
    url = _ws_url(client)
    assert len(url.rsplit("/", 1)[1]) == 32


# ------------------------------------------------------------------ B-07 defusedxml


def test_xml_entity_attacks_are_rejected(tmp_path: Path) -> None:
    """XXE / billion laughs in a sheet: the reader refuses the file (no entity expansion)."""
    from dora_roi.io.xlsx_read import SpreadsheetError, iter_sheets

    src = write_workbook(build_valid_register(), tmp_path / "ok.xlsx")
    evil = tmp_path / "evil.xlsx"
    dtd = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">'
           '<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>')
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(evil, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/sharedStrings.xml":
                text = data.decode().split("?>", 1)[1]
                text = text.replace("<t>c0010</t>", "<t>&xxe;&b;</t>", 1)
                data = (dtd + text).encode()
            zout.writestr(item, data)
    with pytest.raises(SpreadsheetError):
        list(iter_sheets(evil))
    r = TestClient(create_app()).post("/import", files={"file": ("evil.xlsx", evil.read_bytes())})
    assert r.status_code == 400 and "/etc/passwd" not in r.text and "root:x:0" not in r.text


# ------------------------------------------------------------------ B-08 / B-09 performance & locks


def test_edit_is_incremental_and_fast() -> None:
    ws = Workspace("s", register_to_raw(generate_sample(inject_errors=False).source_register))
    row = ws.table("B_02.02").rows[0].row
    assert row is not None
    started = time.monotonic()
    for value in ("AT", "IT", "FR", "DE"):
        ws.edit("B_02.02", row, "c0120", value)
        assert ws.report is not None
    assert (time.monotonic() - started) / 4 < 1.0
    assert len(ws.versions) == 5
    old = ws.register_at(2)
    assert any(s.governing_law_country == "AT" for s in old.b_02_02 if s.row == row)


def test_concurrent_edits_are_serialised() -> None:
    ws = Workspace("s", register_to_raw(build_valid_register()))
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for j in range(10):
                ws.edit("B_02.01", 4, "c0050", str(1000 + i * 100 + j))
                assert ws.report.record_counts["B_02.01"] == 1
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(ws.changes) == 80 and len(ws.versions) == 81
    assert ws.changes[-1].new == ws.row("B_02.01", 4).values["c0050"]


def test_versions_reconstruct_add_and_delete() -> None:
    ws = Workspace("s", register_to_raw(build_valid_register()))
    n = ws.add_row("B_06.01", {"c0010": "F-X"})
    ws.delete_row("B_02.02", 4)
    assert len(ws.register.b_02_02) == 0
    v_after_add = ws.versions[1].number
    reg = ws.register_at(v_after_add)
    assert any(f.function_id == "F-X" for f in reg.b_06_01) and len(reg.b_02_02) == 1
    assert len(ws.register_at(1).b_06_01) == 1
    assert n in {r.row for r in ws.table("B_06.01").rows}


# ------------------------------------------------------------------ B-03 failure impact


def test_failure_impact_includes_subcontracting() -> None:
    reg = generate_sample(inject_errors=False).register
    code = next(p.provider_code for p in reg.b_05_01 if p.legal_name == "Nimbus Cloud Inc.")
    assert code
    impact = failure_impact(reg, code)
    assert len(impact.critical) == 16
    assert impact.critical_direct == 1 and impact.critical_indirect_only == 15
    assert impact.shortest_rto == 4 and len(impact.entities) == 3
    via = {v for f in impact.functions for v in f.via}
    assert "Nimbus Cloud Services EMEA Ltd" in via
    a = analyse(reg)
    nimbus = next(p for p in a.providers if p.code == code)
    assert nimbus.critical_functions == 1 and nimbus.critical_functions_incl_indirect == 16
    assert any(g.critical_functions_incl_indirect > g.critical_functions for g in a.groups)
    assert failure_impact(reg, "UNKNOWN").functions == []


def test_provider_page_shows_failure_impact(client: TestClient) -> None:
    url = _ws_url(client, "clean")
    page = client.get(url + "/register/B_05.01?q=Nimbus+Cloud+Inc").text
    code = page.split("/provider/")[1].split('"')[0]
    p = client.get(url + "/provider/" + code).text
    assert "Failure impact" in p and "16 critical or important function(s) affected" in p
    assert "via Nimbus Cloud Services EMEA Ltd" in p or "via " in p


# ------------------------------------------------------------------ B-10 material diff


def test_diff_separates_administrative_changes() -> None:
    d = diff_registers(generate_previous_year().register,
                       generate_sample(inject_errors=False).register)
    functions = d.get("B_06.01")
    assert len(functions.changed) == 31 and functions.material_changed == []
    contracts = d.get("B_02.01")
    assert contracts.material_changed == [] and len(contracts.changed) > 100  # -8 % costs
    assert d.get("B_02.02").material_total > 0


def test_compare_page_material_toggle(client: TestClient) -> None:
    r = client.post("/sample", data={"variant": "pair"}, follow_redirects=False)
    loc = r.headers["location"]
    page = client.get(loc).text
    assert "Administrative only" in page and "Show administrative changes" in page
    page_all = client.get(loc + "&all=1").text
    assert "Hide administrative changes" in page_all
    assert page_all.count("(administrative)") > page.count("(administrative)")


# ------------------------------------------------------------------ B-11 audit trail


def test_audit_trail_page_and_csv(client: TestClient) -> None:
    client.post("/user", data={"name": "Lena Berger\x07", "next": "/"})
    url = _ws_url(client, "clean")
    client.post(url + "/cell", data={"template": "B_02.01", "row": "4", "column": "c0050",
                                     "value": "=1+2"})
    page = client.get(url + "/audit").text
    assert "Lena Berger" in page and "Value changed" in page
    text = client.get(url + "/download/audit.csv").content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][:3] == ["timestamp_utc", "user", "action"]
    assert rows[1][1] == "Lena Berger" and rows[1][8] == "'=1+2"
    assert clean_user("  x\ny  ") == "xy" and len(clean_user("a" * 200)) == 80


def test_audit_csv_function() -> None:
    ws = Workspace("s", register_to_raw(build_valid_register()))
    ws.edit("B_02.01", 4, "c0050", "5", user="Thomas")
    out = audit_csv(ws)
    assert "Thomas" in out and "Annual expense" in out


# ------------------------------------------------------------------ B-12 accepting findings


def test_accept_warning_but_not_error() -> None:
    ws = Workspace("s", register_to_raw(generate_sample(inject_errors=False).source_register))
    info = next(f for f in ws.report.findings if f.rule_id == "XRF-014")
    with pytest.raises(EditError):
        ws.accept(info, "  ")
    acc = ws.accept(info, "Swiss holding is outside the DORA scope", user="Lena")
    assert not any(f.rule_id == "XRF-014" for f in ws.report.findings)
    assert ws.report.accepted[0].accepted_reason == acc.reason
    assert ws.quality.score == 100
    assert ws.changes[-1].kind == "accept"
    ws.unaccept(acc.key)
    assert any(f.rule_id == "XRF-014" for f in ws.report.findings)
    with pytest.raises(EditError):
        ws.unaccept("nope")
    ws.edit("B_02.02", ws.table("B_02.02").rows[0].row or 0, "c0120", "")
    error = next(f for f in ws.report.findings if f.severity is Severity.ERROR)
    with pytest.raises(EditError, match="cannot be accepted"):
        ws.accept(error, "no")


def test_accept_via_web(client: TestClient) -> None:
    url = _ws_url(client, "clean")
    page = client.get(url + "/fix?template=B_01.02").text
    assert "Accept with justification" in page
    key = page.split('name="key" value="')[1].split('"')[0]
    r = client.post(url + "/accept", data={"key": key, "reason": "Out of scope holding"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert client.get("/api" + url).json()["score"] == 100
    page = client.get(url + "/fix").text
    assert "Accepted findings" in page and "Out of scope holding" in page
    assert client.post(url + "/accept", data={"key": "x", "reason": "y"}).status_code == 404
    assert client.post(url + "/unaccept", data={"key": key}, follow_redirects=False
                       ).status_code == 303
    assert client.post(url + "/unaccept", data={"key": key}).status_code == 404


def test_accept_empty_reason_rejected(client: TestClient) -> None:
    url = _ws_url(client, "clean")
    page = client.get(url + "/fix?template=B_01.02").text
    key = page.split('name="key" value="')[1].split('"')[0]
    assert client.post(url + "/accept", data={"key": key, "reason": " "}).status_code == 400
