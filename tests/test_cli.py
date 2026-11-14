from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from dora_roi.cli import main
from dora_roi.io.csv_folder import write_csv_folder
from dora_roi.io.excel import write_workbook

from conftest import build_valid_register


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def good_xlsx(tmp_path: Path) -> Path:
    return write_workbook(build_valid_register(), tmp_path / "good.xlsx")


@pytest.fixture
def bad_csv(tmp_path: Path) -> Path:
    reg = build_valid_register()
    reg.b_07_01[0].exit_plan = False
    reg.b_02_02[0].data_location_processing = None
    return write_csv_folder(reg, tmp_path / "bad")


def test_version_and_help(runner: CliRunner) -> None:
    assert "roi, version" in runner.invoke(main, ["--version"]).output
    out = runner.invoke(main, ["--help"]).output
    for cmd in ("validate", "report", "export", "template", "rules"):
        assert cmd in out


def test_validate_text_pass(runner: CliRunner, good_xlsx: Path) -> None:
    res = runner.invoke(main, ["validate", str(good_xlsx)])
    assert res.exit_code == 0, res.output
    assert res.output.startswith("PASSED")


def test_validate_fail_and_formats(runner: CliRunner, bad_csv: Path, tmp_path: Path) -> None:
    res = runner.invoke(main, ["validate", str(bad_csv)])
    assert res.exit_code == 1 and "BUS-019" in res.output
    res = runner.invoke(main, ["validate", str(bad_csv), "-f", "json"])
    data = json.loads(res.stdout)
    assert data["passed"] is False
    out = tmp_path / "r.html"
    res = runner.invoke(main, ["validate", str(bad_csv), "-f", "html", "-o", str(out)])
    assert res.exit_code == 1 and out.read_text().startswith("<!doctype html>")
    assert "Validation FAILED" in res.stderr
    res = runner.invoke(main, ["validate", str(bad_csv), "--fail-on", "never", "-f", "md"])
    assert res.exit_code == 0 and "# DORA Register" in res.stdout


def test_validate_disable_downgrade_and_fail_on_warning(runner: CliRunner, bad_csv: Path) -> None:
    res = runner.invoke(main, ["validate", str(bad_csv), "--disable", "bus-019"])
    assert res.exit_code == 0 and "BUS-006" in res.output
    res = runner.invoke(main, ["validate", str(bad_csv), "--downgrade", "BUS-019",
                               "--fail-on", "warning"])
    assert res.exit_code == 1 and "PASSED" in res.output
    res = runner.invoke(main, ["validate", str(bad_csv), "--downgrade", "BUS-019"])
    assert res.exit_code == 0


def test_validate_reference_date(runner: CliRunner, good_xlsx: Path) -> None:
    res = runner.invoke(main, ["validate", str(good_xlsx), "--reference-date", "2028-01-01",
                               "--fail-on", "warning"])
    assert res.exit_code == 1 and "BUS-017" in res.output


def test_validate_input_errors(runner: CliRunner, tmp_path: Path) -> None:
    res = runner.invoke(main, ["validate", str(tmp_path / "nope.xlsx")])
    assert res.exit_code == 2
    txt = tmp_path / "x.txt"
    txt.write_text("x")
    res = runner.invoke(main, ["validate", str(txt)])
    assert res.exit_code == 2 and "Unsupported input" in res.output
    bad_map = tmp_path / "m.json"
    bad_map.write_text("[]")
    res = runner.invoke(main, ["validate", str(tmp_path), "--code-map", str(bad_map)])
    assert res.exit_code == 2 and "invalid code map" in res.output


def test_report(runner: CliRunner, good_xlsx: Path, tmp_path: Path) -> None:
    out = tmp_path / "exec.html"
    vr = tmp_path / "v.md"
    js = tmp_path / "a.json"
    res = runner.invoke(main, ["report", str(good_xlsx), "-o", str(out), "--client", "ACME",
                               "--validation-report", str(vr), "--json", str(js)])
    assert res.exit_code == 0, res.output
    assert "ACME" in out.read_text()
    assert vr.read_text().startswith("# DORA Register")
    assert json.loads(js.read_text())["totals"]["contracts"] == 1


def test_export_formats(runner: CliRunner, good_xlsx: Path, tmp_path: Path) -> None:
    res = runner.invoke(main, ["export", str(good_xlsx), "-o", str(tmp_path / "pkg")])
    assert res.exit_code == 0, res.output
    assert "BEST-EFFORT" in res.stderr
    zips = list((tmp_path / "pkg").glob("*.zip"))
    assert len(zips) == 1 and zipfile.is_zipfile(zips[0])
    cmap = tmp_path / "map.json"
    cmap.write_text(json.dumps({"IctServiceType": {"S19": "eba_TA:S19"}}))
    res = runner.invoke(main, ["export", str(good_xlsx), "-o", str(tmp_path / "u"), "--unzipped",
                               "--level", "IND", "--entry-point", "http://example/ep.json",
                               "--code-map", str(cmap)])
    assert res.exit_code == 0, res.output
    folder = next((tmp_path / "u").iterdir())
    assert ".IND_" in folder.name
    assert "http://example/ep.json" in (folder / "reports" / "report.json").read_text()
    assert "eba_TA:S19" in (folder / "reports" / "b_02.02.csv").read_text()
    res = runner.invoke(main, ["export", str(good_xlsx), "--format", "excel",
                               "-o", str(tmp_path / "copy.xlsx")])
    assert res.exit_code == 0 and (tmp_path / "copy.xlsx").exists()
    res = runner.invoke(main, ["export", str(good_xlsx), "--format", "csv",
                               "-o", str(tmp_path / "csv")])
    assert res.exit_code == 0 and (tmp_path / "csv" / "b_05.01.csv").exists()


def test_export_strict(runner: CliRunner, bad_csv: Path, tmp_path: Path) -> None:
    res = runner.invoke(main, ["export", str(bad_csv), "-o", str(tmp_path / "p"), "--strict"])
    assert res.exit_code == 1 and "refused" in res.stderr
    res = runner.invoke(main, ["export", str(bad_csv), "-o", str(tmp_path / "p")])
    assert res.exit_code == 0 and "does not pass validation" in res.stderr


def test_template(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "t.xlsx"
    res = runner.invoke(main, ["template", str(out)])
    assert res.exit_code == 0 and out.exists()


def test_rules(runner: CliRunner) -> None:
    res = runner.invoke(main, ["rules"])
    assert res.exit_code == 0 and "BUS-019" in res.output
    data = json.loads(runner.invoke(main, ["rules", "-f", "json"]).output)
    assert any(r["id"] == "XRF-003" for r in data)
    md = runner.invoke(main, ["rules", "-f", "md"]).output
    assert md.startswith("# Regulatory mapping")
