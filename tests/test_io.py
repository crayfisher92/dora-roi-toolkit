from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import ENTITY, build_valid_register
from openpyxl import Workbook, load_workbook

from dora_roi.api import validate_path
from dora_roi.io.csv_folder import read_csv_folder, register_to_csv_texts, write_csv_folder
from dora_roi.io.excel import read_workbook, write_blank_template, write_workbook
from dora_roi.io.loader import InputFormat, UnsupportedInputError, detect_format, load, save
from dora_roi.io.tables import column_hint, template_code_for
from dora_roi.io.xbrl_csv import (
    XbrlCsvOptions,
    build_package_files,
    export_xbrl_csv,
    is_xbrl_package,
    load_code_map,
    package_name,
    read_xbrl_csv,
)
from dora_roi.model import TEMPLATE_MODELS, ContractSpecific, RegisterOfInformation


def rules(findings: list) -> set[str]:  # type: ignore[type-arg]
    return {f.rule_id for f in findings}


@pytest.mark.parametrize(
    ("name", "code"),
    [("B_02.02", "B_02.02"), ("b_02.02.csv", "B_02.02"), ("B0202", "B_02.02"),
     ("B 07 01", "B_07.01"), ("b_99.01", None), ("README", None), ("B_02.02.CSV", "B_02.02")],
)
def test_template_code_for(name: str, code: str | None) -> None:
    assert template_code_for(name) == code


# ------------------------------------------------------------------------------ Excel


def test_blank_template_structure(tmp_path: Path) -> None:
    path = write_blank_template(tmp_path / "blank.xlsx")
    wb = load_workbook(path)
    assert wb.sheetnames[0] == "README"
    assert wb.sheetnames[-1] == "_codelists"
    assert wb["_codelists"].sheet_state == "hidden"
    for model in TEMPLATE_MODELS:
        ws = wb[model.TEMPLATE]
        codes = [c.value for c in ws[1]]
        assert codes == [s.code for s in model.columns()]
        assert ws.cell(row=2, column=1).value == model.columns()[0].label
        assert ws.freeze_panes == "A4"
    assert wb["B_02.02"].data_validations.dataValidation, "drop-downs expected"
    raw = read_workbook(path)
    assert set(raw.tables) == {m.TEMPLATE for m in TEMPLATE_MODELS}
    assert all(not t.rows for t in raw.tables.values())
    assert not raw.findings


def test_excel_roundtrip(tmp_path: Path) -> None:
    reg = build_valid_register()
    path = write_workbook(reg, tmp_path / "reg.xlsx")
    loaded = load(path)
    assert loaded.input_format is InputFormat.EXCEL
    assert loaded.register.model_dump() == reg.model_dump()
    assert loaded.register.b_02_02[0].row == 4
    assert loaded.register.b_02_02[0].source == "reg.xlsx:B_02.02"
    _, report = validate_path(path)
    assert report.passed and not report.findings


def test_excel_tolerant_import(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "b0202"
    ws.append(["Register extract – do not edit"])
    ws.append([])
    model = ContractSpecific
    ws.append([s.label for s in model.columns()][:3] + ["Comment"])  # labels as header
    ws.append([" C-9 ", ENTITY, None, "ignored"])
    ws.append([None, None, None, None])
    ws.append(["C-10", 12345, None, None])
    wb.create_sheet("Notes")
    dup = wb.create_sheet("B_02.02")
    dup.append(["c0010"])
    nohdr = wb.create_sheet("B_05.01")
    nohdr.append(["just", "data"])
    wb.save(tmp_path / "t.xlsx")

    raw = read_workbook(tmp_path / "t.xlsx")
    table = raw.tables["B_02.02"]
    assert [r.row for r in table.rows] == [4, 6]
    assert table.rows[0].values["c0010"] == " C-9 "
    found = rules(raw.findings)
    assert {"IMP-001", "IMP-002", "IMP-004"} <= found
    loaded = load(tmp_path / "t.xlsx")
    assert loaded.register.b_02_02[0].contract_ref == "C-9"
    # numeric LEI is coerced to text then rejected as LEI
    assert "FLD-002" in rules(loaded.findings)


def test_excel_unknown_column(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "B_02.01"
    ws.append(["c0010", "c0990", "c0050"])
    ws.append(["C-1", "x", 1000])
    wb.save(tmp_path / "u.xlsx")
    raw = read_workbook(tmp_path / "u.xlsx")
    imp3 = [f for f in raw.findings if f.rule_id == "IMP-003"]
    assert len(imp3) == 1 and imp3[0].column == "c0990"
    assert raw.tables["B_02.01"].rows[0].values == {"c0010": "C-1", "c0050": 1000}


def test_column_hint_mentions_codes_and_condition() -> None:
    spec = ContractSpecific.column("data_location_storage")
    assert "Conditional" in column_hint(spec.col) and "c0140" in column_hint(spec.col)
    assert "S19" in column_hint(ContractSpecific.column("service_type").col)


# ------------------------------------------------------------------------------ CSV


def test_csv_roundtrip(tmp_path: Path) -> None:
    reg = build_valid_register()
    folder = write_csv_folder(reg, tmp_path / "csv")
    assert (folder / "b_02.02.csv").exists()
    loaded = load(folder)
    assert loaded.input_format is InputFormat.CSV
    assert loaded.register.model_dump() == reg.model_dump()
    assert loaded.register.b_02_02[0].row == 2


def test_csv_semicolon_bom_and_names(tmp_path: Path) -> None:
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "B_02.01.csv").write_text("﻿c0010;c0020;c0040;c0050\nC-1;Standalone;EUR;100\n",
                                        encoding="utf-8")
    (folder / "notes.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (folder / "parameters.csv").write_text("name,value\n", encoding="utf-8")
    raw = read_csv_folder(folder)
    assert raw.tables["B_02.01"].rows[0].values["c0020"] == "Standalone"
    assert "IMP-001" in rules(raw.findings)
    loaded = load(folder)
    assert loaded.register.b_02_01[0].contract_type is not None


def test_csv_zip(tmp_path: Path) -> None:
    texts = register_to_csv_texts(build_valid_register())
    zpath = tmp_path / "csvs.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for name, text in texts.items():
            zf.writestr(f"export/{name}", text)
        zf.writestr("export/", "")
    assert detect_format(zpath) is InputFormat.CSV
    loaded = load(zpath)
    assert loaded.register.model_dump() == build_valid_register().model_dump()


def test_save_dispatch(tmp_path: Path) -> None:
    reg = build_valid_register()
    assert save(reg, tmp_path / "a.xlsx").suffix == ".xlsx"
    assert save(reg, tmp_path / "folder").is_dir()


# ------------------------------------------------------------------------------ xBRL-CSV


def test_xbrl_package_contents(tmp_path: Path) -> None:
    reg = build_valid_register()
    opts = XbrlCsvOptions(created_at=datetime(2026, 1, 15, 8, 30, tzinfo=UTC),
                          code_map={"IctServiceType": {"S19": "eba_TA:S19"}})
    result = export_xbrl_csv(reg, tmp_path, opts)
    assert result.path.suffix == ".zip"
    assert result.package_name == f"{ENTITY}.CON_DE_DORA010100_DORA_2025-12-31_20260115083000000"
    assert any("BEST-EFFORT" in w for w in result.warnings)
    with zipfile.ZipFile(result.path) as zf:
        names = zf.namelist()
        root = result.package_name
        assert f"{root}/META-INF/reportPackage.json" in names
        report = json.loads(zf.read(f"{root}/reports/report.json"))
        assert report["documentInfo"]["documentType"] == "https://xbrl.org/2021/xbrl-csv"
        params = zf.read(f"{root}/reports/parameters.csv").decode()
        assert f"entityID,rs:{ENTITY}.CON" in params and "refPeriod,2025-12-31" in params
        assert "baseCurrency,iso4217:EUR" in params
        fi = zf.read(f"{root}/reports/FilingIndicators.csv").decode()
        assert "B_02.02,true" in fi and "B_01.03,false" in fi
        b0202 = zf.read(f"{root}/reports/b_02.02.csv").decode()
        assert "eba_GA:DE" in b0202 and "eba_TA:S19" in b0202
        assert f"{root}/reports/b_01.03.csv" not in names
    assert is_xbrl_package(result.path)
    loaded = load(result.path, code_map=opts.code_map)
    assert loaded.input_format is InputFormat.XBRL_CSV
    assert loaded.register.model_dump() == reg.model_dump()
    assert not loaded.findings  # filing indicators explain the absent templates


def test_xbrl_unzipped_and_explicit_zip(tmp_path: Path) -> None:
    reg = build_valid_register()
    res = export_xbrl_csv(reg, tmp_path / "pkg", unzipped=True)
    assert res.path.is_dir() and (res.path / "reports" / "report.json").exists()
    assert detect_format(res.path) is InputFormat.XBRL_CSV
    assert load(res.path).register.model_dump() == reg.model_dump()
    res2 = export_xbrl_csv(reg, tmp_path / "named.zip")
    assert res2.path.name == "named.zip" and res2.package_name == "named"
    res3 = export_xbrl_csv(reg, tmp_path / "named2.zip", unzipped=True)
    assert res3.path.is_dir() and res3.path.name == "named2"
    raw = read_xbrl_csv(res2.path)
    assert raw.tables["B_02.02"].rows[0].values["c0120"] == "DE"


def test_xbrl_empty_register_placeholders() -> None:
    files, warnings = build_package_files(RegisterOfInformation())
    assert "entityID,rs:UNKNOWNLEI.CON" in files["reports/parameters.csv"]
    assert any("no valid LEI" in w for w in warnings)
    assert any("no reporting date" in w for w in warnings)
    name = package_name(RegisterOfInformation(), XbrlCsvOptions(package_name="X"))
    assert name == "X"


def test_load_code_map(tmp_path: Path) -> None:
    good = tmp_path / "map.json"
    good.write_text(json.dumps({"Criticality": {"CRITICAL": "eba_BT:x28"}}))
    assert load_code_map(good) == {"Criticality": {"CRITICAL": "eba_BT:x28"}}
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    with pytest.raises(ValueError):
        load_code_map(bad)


def test_detect_format_errors(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        detect_format(tmp_path / "missing.xlsx")
    txt = tmp_path / "x.txt"
    txt.write_text("hi")
    with pytest.raises(UnsupportedInputError):
        detect_format(txt)
    fake_zip = tmp_path / "fake.zip"
    fake_zip.write_text("not a zip")
    with pytest.raises(UnsupportedInputError):
        detect_format(fake_zip)
