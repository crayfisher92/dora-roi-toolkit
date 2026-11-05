from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dora_roi.io.csv_folder import register_to_csv_texts
from dora_roi.io.excel import write_workbook
from dora_roi.web.app import Store, create_app

from conftest import build_valid_register


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Store(capacity=3)))


def _upload(client: TestClient, name: str, data: bytes) -> object:
    return client.post("/upload", files={"file": (name, data)}, follow_redirects=False)


def test_index_and_health(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200 and "Validate and analyse" in r.text
    assert client.get("/api/health").json()["status"] == "ok"


def test_template_download(client: TestClient) -> None:
    r = client.get("/template.xlsx")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert "attachment" in r.headers["content-disposition"]


def test_upload_xlsx_and_views(client: TestClient, tmp_path: Path) -> None:
    path = write_workbook(build_valid_register(), tmp_path / "reg.xlsx")
    r = _upload(client, "reg.xlsx", path.read_bytes())
    assert r.status_code == 303  # type: ignore[attr-defined]
    url = r.headers["location"]  # type: ignore[attr-defined]
    page = client.get(url)
    assert page.status_code == 200 and "Passed." in page.text and "Test Bank AG" in page.text
    assert "Concentration dashboard" in page.text
    assert client.get(url + "/validation.json").json()["passed"] is True
    assert client.get(url + "/validation.md").text.startswith("# DORA Register")
    assert "<!doctype html>" in client.get(url + "/validation.html").text
    assert "Key messages" in client.get(url + "/executive.html").text
    assert client.get(url + "/analysis.json").json()["totals"]["contracts"] == 1
    z = client.get(url + "/xbrl-csv.zip")
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert any(n.endswith("reports/report.json") for n in names)
    assert "reg.xlsx" in client.get("/").text


def test_upload_csv_zip(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in register_to_csv_texts(build_valid_register()).items():
            zf.writestr(name, text)
    r = _upload(client, "csvs.zip", buf.getvalue())
    assert r.status_code == 303  # type: ignore[attr-defined]


def test_upload_rejections(client: TestClient) -> None:
    r = _upload(client, "notes.txt", b"hello")
    assert r.status_code == 200 and "Unsupported file type" in r.text  # type: ignore[attr-defined]
    r = _upload(client, "broken.xlsx", b"not really excel")
    assert "Could not read" in r.text  # type: ignore[attr-defined]
    r = _upload(client, "bad.zip", b"PK-not-a-zip")
    assert "Could not read" in r.text  # type: ignore[attr-defined]


def test_upload_too_large(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import dora_roi.web.app as webapp

    monkeypatch.setattr(webapp, "MAX_UPLOAD_BYTES", 10)
    r = _upload(client, "big.xlsx", b"x" * 100)
    assert "too large" in r.text  # type: ignore[attr-defined]


def test_sample_and_store_eviction(client: TestClient) -> None:
    urls = []
    for clean in ("false", "true", "true", "true"):
        r = client.post("/sample", data={"clean": clean}, follow_redirects=False)
        assert r.status_code == 303
        urls.append(r.headers["location"])
    assert client.get(urls[0]).status_code == 404  # evicted (capacity 3)
    page = client.get(urls[-1])
    assert "Alpenrand" in page.text and "Passed" in page.text
    assert client.get("/r/doesnotexist").status_code == 404
