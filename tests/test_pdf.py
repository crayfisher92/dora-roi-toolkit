"""PDF reports (WeasyPrint) and print variants of the HTML reports."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from pypdf import PdfReader

import dora_roi.reporting.pdf as pdf_mod
from dora_roi.cli import main
from dora_roi.io.excel import write_workbook
from dora_roi.reporting import validation_report
from dora_roi.reporting.executive import render_executive_pdf, render_executive_summary
from dora_roi.reporting.pdf import PdfUnavailableError, html_to_pdf, pdf_available
from dora_roi.reporting.validation_report import render_html, render_pdf
from dora_roi.sample import generate_sample
from dora_roi.validation import ValidationReport, validate
from dora_roi.web.app import create_app

pytestmark = pytest.mark.skipif(not pdf_available(), reason="WeasyPrint/Pango not installed")


@pytest.fixture(scope="module")
def sample() -> tuple[Any, ValidationReport]:
    res = generate_sample()
    return res.register, validate(res.register, parse_findings=res.findings)


def _text(data: bytes) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(data))
    return len(reader.pages), "\n".join(p.extract_text() for p in reader.pages)


def test_executive_pdf(sample: tuple[Any, ValidationReport]) -> None:
    register, report = sample
    data = render_executive_pdf(register, report, client_name="Alpenrand Test")
    assert data[:5] == b"%PDF-"
    pages, text = _text(data)
    assert pages >= 4
    assert "Alpenrand Test" in text and "Key messages" in text
    assert "Provider concentration" in text and f"Page 1 of {pages}" in text
    assert "Legal entities" in text  # the collapsible table is expanded in the PDF


def test_validation_pdf_truncates(sample: tuple[Any, ValidationReport],
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    _, report = sample
    monkeypatch.setattr(validation_report, "MAX_PDF_FINDINGS", 5)
    pages, text = _text(render_pdf(report))
    assert "Validation report".upper() in text.upper() and "FLD-005" in text
    assert f"Showing the first 5 of {len(report.findings)} findings" in text
    assert pages >= 2


def test_print_variants(sample: tuple[Any, ValidationReport]) -> None:
    register, report = sample
    for html in (render_html(report, pdf=True), render_executive_summary(register, report,
                                                                         pdf=True)):
        assert "<script" not in html and "<details open>" in html
        assert "@page" in html and "counter(pages)" in html
    for html in (render_html(report), render_executive_summary(register, report)):
        assert "<script" in html and "<details open>" not in html
    exec_html = render_executive_summary(register, report)
    assert 'fill="#2a78d6"' in exec_html  # charts carry their colours without CSS


def test_external_resources_are_never_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    original = pdf_mod._refuse

    def spy(url: str, *a: Any, **k: Any) -> Any:
        calls.append(url)
        return original(url, *a, **k)

    monkeypatch.setattr(pdf_mod, "_refuse", spy)
    html = ('<html><head><title>x</title><link rel="stylesheet" href="http://example.invalid/'
            'x.css"></head><body><p>secret</p><img src="file:///etc/passwd">'
            '<img src="https://example.invalid/track.png"></body></html>')
    data = html_to_pdf(html)
    assert data[:5] == b"%PDF-" and len(calls) == 3
    with pytest.raises(ValueError, match="disabled"):
        original("file:///etc/passwd")


def test_cli_pdf(tmp_path: Path) -> None:
    xlsx = write_workbook(generate_sample().source_register, tmp_path / "s.xlsx")
    runner = CliRunner()
    res = runner.invoke(main, ["validate", str(xlsx), "-f", "pdf", "-o", str(tmp_path / "v.pdf"),
                               "--fail-on", "never"])
    assert res.exit_code == 0 and (tmp_path / "v.pdf").read_bytes()[:5] == b"%PDF-"
    assert runner.invoke(main, ["validate", str(xlsx), "-f", "pdf"]).exit_code == 2
    res = runner.invoke(main, ["report", str(xlsx), "-o", str(tmp_path / "e.pdf"),
                               "--validation-report", str(tmp_path / "v2.pdf")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "e.pdf").read_bytes()[:5] == b"%PDF-"
    assert (tmp_path / "v2.pdf").read_bytes()[:5] == b"%PDF-"


def test_web_pdf_downloads() -> None:
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "dirty"}, follow_redirects=False
                      ).headers["location"]
    page = client.get(url + "/export").text
    assert "/download/executive.pdf" in page and "/download/validation.pdf" in page
    for kind in ("executive", "validation"):
        r = client.get(f"{url}/download/{kind}.pdf")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert f"{kind}.pdf" in r.headers["content-disposition"]


def test_without_weasyprint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real = pdf_mod.importlib.util.find_spec
    monkeypatch.setattr(pdf_mod.importlib.util, "find_spec",
                        lambda name, *a: None if name == "weasyprint" else real(name, *a))
    assert not pdf_available()
    with pytest.raises(PdfUnavailableError, match=r"dora-roi-toolkit\[pdf\]"):
        html_to_pdf("<p>x</p>")
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "clean"}, follow_redirects=False
                      ).headers["location"]
    page = client.get(url + "/export").text
    assert "/download/executive.pdf" not in page and "Save as PDF" in page
    assert client.get(url + "/download/executive.pdf").status_code == 404
    xlsx = write_workbook(generate_sample().source_register, tmp_path / "s.xlsx")
    res = CliRunner().invoke(main, ["report", str(xlsx), "-o", str(tmp_path / "e.pdf")])
    assert res.exit_code == 2 and "WeasyPrint" in res.output
