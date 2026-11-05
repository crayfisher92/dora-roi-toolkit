"""Large registers: reader normalisation, writer fidelity and the scale generator."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from dora_roi.io.excel import read_workbook, write_raw_workbook, write_workbook
from dora_roi.io.loader import load
from dora_roi.io.xlsx_read import SpreadsheetError, cell_value, iter_sheets
from dora_roi.model import ContractSpecific, Function
from dora_roi.sample.large import generate_large
from dora_roi.validation import validate

from conftest import build_valid_register


@pytest.mark.parametrize(("raw", "expected"), [
    ("", None), (None, None), ("x", "x"), (60.0, 60), (1.5, 1.5), (True, True),
    (date(2020, 1, 2), date(2020, 1, 2)), (time(3, 4), "03:04:00"),
    (timedelta(hours=5), "5:00:00"), (2.0**60, 2.0**60), (7, 7),
])
def test_cell_value_normalisation(raw: object, expected: object) -> None:
    assert cell_value(raw) == expected


def test_reader_keeps_sheet_coordinates(tmp_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "S"
    ws["C3"] = "x"
    ws["D3"] = 60
    ws["E5"] = datetime(2020, 1, 2, 3, 4)
    wb.create_sheet("T")["A1"] = "y"
    wb.save(tmp_path / "t.xlsx")
    sheets = dict(iter_sheets(tmp_path / "t.xlsx"))
    rows = sheets["S"]
    assert rows[2][2:4] == ["x", 60] and rows[0] == [None] * len(rows[0])  # A1-based
    assert rows[4][4] == datetime(2020, 1, 2, 3, 4)
    assert dict(iter_sheets(tmp_path / "t.xlsx", only="T")) == {"T": [["y"]]}
    with pytest.raises(SpreadsheetError, match="not found"):
        list(iter_sheets(tmp_path / "t.xlsx", only="nope"))
    (tmp_path / "bad.xlsx").write_bytes(b"PK\x03\x04 broken")
    with pytest.raises((SpreadsheetError, ValueError)):
        list(iter_sheets(tmp_path / "bad.xlsx"))


def test_writer_formats_and_round_trip(tmp_path: Path) -> None:
    reg = build_valid_register()
    reg.b_02_01[0].annual_cost = Decimal("1234.5")
    reg.b_06_01[0].last_assessment_date = date(1899, 12, 31)  # before Excel's epoch
    path = write_workbook(reg, tmp_path / "r.xlsx")
    wb = load_workbook(path)
    assert wb.sheetnames[0] == "README" and wb.active.title == "README"  # type: ignore[union-attr]
    ws = wb["B_02.02"]
    assert ws.freeze_panes == "A4" and ws.cell(1, 1).font.b
    date_col = next(i for i, c in enumerate(ContractSpecific.columns(), start=1)
                    if c.attr == "start_date")
    assert ws.cell(4, date_col).number_format == "yyyy-mm-dd"
    assert ws.cell(4, date_col).is_date
    fn_col = next(i for i, c in enumerate(Function.columns(), start=1)
                  if c.attr == "last_assessment_date")
    assert wb["B_06.01"].cell(4, fn_col).value == "1899-12-31"
    back = load(path).register
    assert back.b_02_01[0].annual_cost == Decimal("1234.5")
    assert back.b_06_01[0].last_assessment_date == date(1899, 12, 31)


def test_raw_writer_keeps_invalid_values(tmp_path: Path) -> None:
    from dora_roi.sample import register_to_raw

    raw = register_to_raw(build_valid_register())
    raw.tables["B_02.02"].rows[0].values["c0120"] = "not a country"
    raw.tables["B_02.02"].rows[0].values["c0070"] = "31.12.2025"
    back = read_workbook(write_raw_workbook(raw, tmp_path / "raw.xlsx"))
    values = back.tables["B_02.02"].rows[0].values
    assert values["c0120"] == "not a country" and values["c0070"] == "31.12.2025"


def test_large_generator_is_valid_and_sized() -> None:
    res = generate_large(contracts=600, providers=120, seed=7)
    counts = res.register.counts()
    assert counts["B_02.01"] == 600 and counts["B_05.01"] == 120
    report = validate(res.register, parse_findings=res.findings)
    assert report.severity_counts()["error"] == 0
    groups = {p.ultimate_parent_code for p in res.register.b_05_01}
    assert len(groups) < counts["B_05.01"]  # some providers belong to groups
    assert res.register.b_05_02  # subcontracting chains present
    assert generate_large(contracts=50, providers=60, seed=7).register.model_dump() == \
        generate_large(contracts=50, providers=60, seed=7).register.model_dump()


def test_critical_checker_matches_supports_critical() -> None:
    reg = generate_large(contracts=300, providers=80, seed=3).register
    check = reg.critical_checker()
    assert [check(s) for s in reg.b_02_02] == [reg.supports_critical(s) for s in reg.b_02_02]
    assert any(check(s) for s in reg.b_02_02) and not all(check(s) for s in reg.b_02_02)


def test_store_evicts_by_row_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from dora_roi.web.app import LRUStore, create_app
    from dora_roi.workspace import Workspace

    store: LRUStore[list[int]] = LRUStore(10, max_weight=5, weight=len)
    store.add("a", [1, 2])
    store.add("b", [1, 2])
    store.add("c", [1, 2])  # 6 > 5: oldest goes
    assert [len(v) for v in store.values()] == [2, 2]
    store.add("huge", list(range(50)))  # newest is always kept
    assert [len(v) for v in store.values()] == [50]

    monkeypatch.setenv("ROI_MAX_STORE_ROWS", "250")
    app = create_app()
    client = TestClient(app)
    first = client.post("/sample", data={"variant": "clean"}, follow_redirects=False)
    rows = next(iter(app.state.workspaces.values())).row_count()
    assert rows > 125  # the sample is larger than half the budget
    client.post("/sample", data={"variant": "clean"}, follow_redirects=False)
    assert len(app.state.workspaces.values()) == 1
    assert client.get(first.headers["location"]).status_code == 404
    assert isinstance(next(iter(app.state.workspaces.values())), Workspace)
    monkeypatch.setenv("ROI_MAX_STORE_ROWS", "nonsense")
    from dora_roi.web.app import max_store_rows

    assert max_store_rows() == 500_000
