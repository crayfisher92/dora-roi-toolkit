"""Import from / export to a folder of CSV files (one file per template).

File names follow the xBRL-CSV convention (``b_02.02.csv``) but variants such as
``B_02.02.csv`` or ``B0202.csv`` are accepted. The first row(s) must contain the column codes
(or labels). Comma, semicolon and tab delimiters are detected automatically; UTF-8 with or
without BOM is expected.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable, Iterable
from pathlib import Path

from dora_roi.io.raw import RawRegister, RawValue
from dora_roi.io.tables import (
    build_table,
    file_name_for,
    import_finding,
    missing_template_findings,
    template_code_for,
)
from dora_roi.model import TEMPLATE_MODELS, RegisterOfInformation

ValueMapper = Callable[[str, str, str], str]


def _sniff(text: str) -> str:
    first = text.splitlines()[0] if text else ""
    counts = {d: first.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def parse_csv_text(text: str) -> list[list[str]]:
    reader = csv.reader(io.StringIO(text), delimiter=_sniff(text))
    return list(reader)


def read_csv_files(
    files: Iterable[tuple[str, str]], source: str, mapper: ValueMapper | None = None
) -> RawRegister:
    """Build a raw register from ``(file name, text)`` pairs.

    ``mapper(template, column, value)`` may translate exported taxonomy values back to
    internal codes (used by the xBRL-CSV reader).
    """
    raw = RawRegister(source=source)
    for name, text in sorted(files):
        code = template_code_for(Path(name).name)
        if code is None:
            raw.findings.append(import_finding(
                "IMP-001", f"File '{name}' does not match an RoI template; ignored",
                source=source))
            continue
        rows = parse_csv_text(text.lstrip("﻿"))
        table = build_table(code, ((i, list(r)) for i, r in enumerate(rows, start=1)),
                            f"{source}:{Path(name).name}", raw.findings)
        if mapper is not None:
            for row in table.rows:
                row.values = {
                    col: (mapper(code, col, v) if isinstance(v, str) else v)
                    for col, v in row.values.items()
                }
        raw.tables[code] = table
    raw.findings.extend(missing_template_findings(raw.tables, source))
    return raw


def read_csv_folder(path: str | Path) -> RawRegister:
    """Read every ``*.csv`` file of ``path`` (non-recursive)."""
    folder = Path(path)
    files: list[tuple[str, str]] = []
    for f in sorted(folder.glob("*.csv")):
        if f.name.lower() in {"parameters.csv", "filingindicators.csv"}:
            continue
        files.append((f.name, f.read_text(encoding="utf-8-sig")))
    return read_csv_files(files, folder.name)


def register_to_csv_texts(
    register: RegisterOfInformation,
    value_mapper: ValueMapper | None = None,
    include_empty: bool = True,
) -> dict[str, str]:
    """Serialise each template to CSV text keyed by file name."""
    out: dict[str, str] = {}
    for model in TEMPLATE_MODELS:
        records = register.records(model.TEMPLATE)
        if not records and not include_empty:
            continue
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        codes = [c.code for c in model.columns()]
        writer.writerow(codes)
        for rec in records:
            row = rec.to_row()
            values: list[str] = []
            for code in codes:
                v = row[code]
                if v is not None and value_mapper is not None:
                    v = value_mapper(model.TEMPLATE, code, v)
                values.append("" if v is None else v)
            writer.writerow(values)
        out[file_name_for(model.TEMPLATE)] = buf.getvalue()
    return out


def write_csv_folder(register: RegisterOfInformation, path: str | Path) -> Path:
    """Write one CSV per template (internal codes, ISO dates) into ``path``."""
    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in register_to_csv_texts(register).items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


__all__ = [
    "RawValue",
    "parse_csv_text",
    "read_csv_files",
    "read_csv_folder",
    "register_to_csv_texts",
    "write_csv_folder",
]
