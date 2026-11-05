"""Fast, safe reading of spreadsheet cell values (python-calamine).

openpyxl spends most of its time building cell objects; on a register with 10 000
contracts that is ~8 s of a ~10 s import. ``python-calamine`` (Rust) reads the same workbook
in well under a second, and its XML parser rejects DTDs and custom entities, so XXE and
entity-expansion attacks fail with an error instead of being processed (``docs/DECISIONS.md``
D-045). Workbooks are written with XlsxWriter.

Values are normalised to what the rest of the toolkit expects from a spreadsheet:

* empty and error cells → ``None``
* integral numbers → ``int`` (calamine reports every number as ``float``)
* dates / datetimes unchanged; times and durations → ISO text
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, time, timedelta
from pathlib import Path
from typing import Any

from python_calamine import CalamineError, CalamineWorkbook, SheetTypeEnum

from dora_roi.io.limits import check_archive
from dora_roi.io.raw import RawValue

__all__ = ["SpreadsheetError", "cell_value", "iter_sheets"]


class SpreadsheetError(ValueError):
    """The file could not be read as a spreadsheet."""


def cell_value(value: Any) -> RawValue:
    if value is None or value == "":
        return None
    if isinstance(value, bool | str | date):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() and abs(value) < 2**53 else value
    if isinstance(value, int):
        return value
    if isinstance(value, time | timedelta):
        return value.isoformat() if isinstance(value, time) else str(value)
    return str(value)


def iter_sheets(path: str | Path, only: str | None = None
                ) -> Iterator[tuple[str, list[list[RawValue]]]]:
    """Yield ``(sheet name, rows)`` for each worksheet, rows starting at spreadsheet row 1.

    The archive is checked against the decompression limits before anything is parsed.
    """
    p = Path(path)
    check_archive(p)
    try:
        wb = CalamineWorkbook.from_path(str(p))
    except (CalamineError, OSError, ValueError) as exc:
        raise SpreadsheetError(f"not a readable spreadsheet: {exc}") from exc
    try:
        names = [m.name for m in wb.sheets_metadata if m.typ == SheetTypeEnum.WorkSheet]
        if only is not None:
            if only not in names:
                raise SpreadsheetError(f"sheet {only!r} not found")
            names = [only]
        for name in names:
            try:
                rows = wb.get_sheet_by_name(name).to_python(skip_empty_area=False)
            except (CalamineError, ValueError) as exc:
                raise SpreadsheetError(f"sheet {name!r} could not be read: {exc}") from exc
            yield name, [[cell_value(v) for v in row] for row in rows]
    finally:
        wb.close()
