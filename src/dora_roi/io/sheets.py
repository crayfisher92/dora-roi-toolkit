"""Small, safe XlsxWriter wrapper for the programme workbooks (assessments, remediation plan).

Same conventions as :mod:`dora_roi.io.excel` (D-045): written in memory (no temporary files
with client data), strings are never turned into formulas, numbers or URLs, and text starting
with a formula trigger gets a quote prefix (CWE-1236).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import xlsxwriter
from xlsxwriter.worksheet import Worksheet

from dora_roi.io.excel import FORMULA_TRIGGERS

HEADER_COLOUR = "#1C5CAB"


class SheetBook:
    """``with SheetBook(path) as book: book.sheet(...)`` writes a workbook of plain tables."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.wb = xlsxwriter.Workbook(str(self.path), {
            "in_memory": True, "strings_to_formulas": False, "strings_to_numbers": False,
            "strings_to_urls": False})
        self.header = self.wb.add_format({"bold": True, "font_color": "#FFFFFF",
                                          "bg_color": HEADER_COLOUR, "pattern": 1,
                                          "text_wrap": True, "valign": "top"})
        self.wrap = self.wb.add_format({"text_wrap": True, "valign": "top"})
        self.wrap_quoted = self.wb.add_format({"text_wrap": True, "valign": "top",
                                               "quote_prefix": True})
        self.date = self.wb.add_format({"num_format": "yyyy-mm-dd", "valign": "top"})
        self.fills: dict[str, Any] = {}

    def fill(self, colour: str) -> Any:
        if colour not in self.fills:
            self.fills[colour] = self.wb.add_format({"bg_color": colour, "pattern": 1,
                                                     "valign": "top", "text_wrap": True})
        return self.fills[colour]

    def write(self, ws: Worksheet, row: int, col: int, value: Any, fmt: Any = None) -> None:
        if value is None or value == "":
            return
        if isinstance(value, str):
            quoted = value[:1] in FORMULA_TRIGGERS
            ws.write_string(row, col, value,
                            self.wrap_quoted if quoted else (fmt or self.wrap))
        elif isinstance(value, bool):
            ws.write_string(row, col, "true" if value else "false", fmt or self.wrap)
        elif isinstance(value, datetime):
            ws.write_datetime(row, col, value.replace(tzinfo=None), fmt or self.date)
        elif isinstance(value, date):
            ws.write_datetime(row, col, datetime(value.year, value.month, value.day),
                              fmt or self.date)
        elif isinstance(value, int | float):
            ws.write_number(row, col, value, fmt)
        else:
            ws.write_string(row, col, str(value), fmt or self.wrap)

    def sheet(self, name: str, headers: Sequence[str], rows: Sequence[Sequence[Any]],
              widths: Sequence[int], *, lists: dict[int, Sequence[str]] | None = None,
              cell_formats: dict[tuple[int, int], Any] | None = None,
              freeze_cols: int = 0, extra_rows: int = 500) -> Worksheet:
        """A table sheet: bold header, frozen header (and ``freeze_cols``), autofilter,
        wrapped text, optional drop-down lists per column index."""
        ws = self.wb.add_worksheet(name[:31])
        for col, title in enumerate(headers):
            ws.write_string(0, col, title, self.header)
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)
        for r, values in enumerate(rows, start=1):
            for c, value in enumerate(values):
                self.write(ws, r, c, value, (cell_formats or {}).get((r, c)))
        ws.freeze_panes(1, freeze_cols)
        if headers:
            ws.autofilter(0, 0, max(len(rows), 1), len(headers) - 1)
        for col, options in (lists or {}).items():
            ws.data_validation(1, col, len(rows) + extra_rows, col,
                               {"validate": "list", "source": list(options),
                                "ignore_blank": True})
        return ws

    def text_sheet(self, name: str, lines: Sequence[str], width: int = 110) -> Worksheet:
        ws = self.wb.add_worksheet(name[:31])
        ws.set_column(0, 0, width)
        for r, line in enumerate(lines):
            self.write(ws, r, 0, line)
        return ws

    def close(self) -> Path:
        self.wb.close()
        return self.path

    def __enter__(self) -> SheetBook:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 tb: TracebackType | None) -> None:
        self.close()
