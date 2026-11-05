from __future__ import annotations

import zipfile
from pathlib import Path

from click.testing import CliRunner

from dora_roi.cli import main
from dora_roi.io.package_check import Status, compare_packages, read_package
from dora_roi.io.xbrl_csv import XbrlCsvOptions, export_xbrl_csv

from conftest import build_valid_register


def _pkg(tmp: Path, name: str = "ours", **opts: object) -> Path:
    return export_xbrl_csv(build_valid_register(), tmp / f"{name}.zip",
                           XbrlCsvOptions(**opts)).path  # type: ignore[arg-type]


def _mutated_reference(src: Path, dst: Path) -> Path:
    """A 'reference' package that differs in the ways an official sample might."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        root = zin.namelist()[0].split("/")[0]
        for n in zin.namelist():
            text = zin.read(n).decode()
            rel = n[len(root) + 1:]
            if rel == "reports/b_02.02.csv":
                lines = text.splitlines()
                lines[0] = lines[0].replace("c0180", "c0181")
                lines[1:] = [ln.replace(",S19,", ",eba_TA:S19,") for ln in lines[1:]]
                text = "\n".join(lines) + "\n"
            if rel == "reports/parameters.csv":
                text = text.replace("rs:", "lei:") + "extraParam,1\n"
            if rel == "reports/report.json":
                text = text.replace("dora/4.0", "dora/4.1")
            zout.writestr(f"REFLEI.CON_DE_DORA010100_DORA_2025-12-31_20260101000000000/{rel}",
                          text)
        zout.writestr("REFLEI.CON_DE_DORA010100_DORA_2025-12-31_20260101000000000/reports/"
                      "b_99.99.csv", "c0010\n")
    return dst


def test_identical_packages_pass(tmp_path: Path) -> None:
    a = _pkg(tmp_path, "a")
    result = compare_packages(a, a)
    assert not result.failures
    assert all(c.status is Status.OK for c in result.checks)
    assert "0 failures" in result.to_markdown()


def test_differences_detected(tmp_path: Path) -> None:
    ours = _pkg(tmp_path)
    ref = _mutated_reference(ours, tmp_path / "ref.zip")
    result = compare_packages(ref, ours)
    text = result.to_markdown()
    assert "extends" in text and "dora/4.1" in text
    assert "'extraParam' missing" in text
    assert "'entityID': value style rs:* vs reference lei:*" in text
    assert "columns only in reference ['c0181']" in text
    assert "c0060: ours ['text'] vs reference ['eba_TA:*']" in text
    assert "b_99.99.csv in reference but not in ours" in text
    assert result.failures


def test_read_folder_package_and_naming(tmp_path: Path) -> None:
    folder = export_xbrl_csv(build_valid_register(), tmp_path, unzipped=True).path
    pkg = read_package(folder)
    assert "reports/report.json" in pkg.files and "META-INF/reportPackage.json" in pkg.files
    other = _pkg(tmp_path, "x")
    naming = [c for c in compare_packages(folder, other).checks if c.area == "naming"]
    assert naming[0].status is Status.WARN


def test_cli_check_package(tmp_path: Path) -> None:
    runner = CliRunner()
    ours = _pkg(tmp_path)
    res = runner.invoke(main, ["check-package", str(ours), "--ours", str(ours)])
    assert res.exit_code == 0 and "Package comparison" in res.output
    ref = _mutated_reference(ours, tmp_path / "ref.zip")
    out = tmp_path / "cmp.md"
    res = runner.invoke(main, ["check-package", str(ref), "-o", str(out)])
    assert res.exit_code == 1 and "❌" in out.read_text()
