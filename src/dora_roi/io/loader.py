"""Format auto-detection and the high-level ``load`` / ``save`` entry points."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dora_roi.io.csv_folder import read_csv_files, read_csv_folder, write_csv_folder
from dora_roi.io.excel import read_workbook, write_workbook
from dora_roi.io.parse import parse_raw
from dora_roi.io.raw import RawRegister
from dora_roi.io.xbrl_csv import CodeMap, is_xbrl_package, read_xbrl_csv
from dora_roi.model import RegisterOfInformation
from dora_roi.validation import Finding


class InputFormat(StrEnum):
    EXCEL = "excel"
    CSV = "csv"
    XBRL_CSV = "xbrl-csv"


class UnsupportedInputError(ValueError):
    """Raised when a path cannot be recognised as an RoI input."""


@dataclass
class LoadResult:
    register: RegisterOfInformation
    findings: list[Finding] = field(default_factory=list)
    source: str = ""
    input_format: InputFormat = InputFormat.EXCEL


def detect_format(path: str | Path) -> InputFormat:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.is_dir():
        return InputFormat.XBRL_CSV if is_xbrl_package(p) else InputFormat.CSV
    suffix = p.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return InputFormat.EXCEL
    if suffix == ".zip":
        if is_xbrl_package(p):
            return InputFormat.XBRL_CSV
        if zipfile.is_zipfile(p):
            return InputFormat.CSV
    raise UnsupportedInputError(
        f"Unsupported input '{p.name}': expected an .xlsx workbook, a folder of CSV files, a zip "
        "of CSV files or an xBRL-CSV package"
    )


def _read_csv_zip(path: Path) -> RawRegister:
    with zipfile.ZipFile(path) as zf:
        files = [
            (n.rsplit("/", 1)[-1], zf.read(n).decode("utf-8-sig"))
            for n in zf.namelist()
            if n.lower().endswith(".csv") and not n.endswith("/")
        ]
    return read_csv_files(files, path.name)


def load_raw(path: str | Path, code_map: CodeMap | None = None) -> tuple[RawRegister, InputFormat]:
    p = Path(path)
    fmt = detect_format(p)
    if fmt is InputFormat.EXCEL:
        return read_workbook(p), fmt
    if fmt is InputFormat.XBRL_CSV:
        return read_xbrl_csv(p, code_map), fmt
    if p.is_dir():
        return read_csv_folder(p), fmt
    return _read_csv_zip(p), fmt


def load(path: str | Path, code_map: CodeMap | None = None) -> LoadResult:
    """Load any supported input into a typed register plus import/field findings."""
    raw, fmt = load_raw(path, code_map)
    parsed = parse_raw(raw)
    return LoadResult(parsed.register, parsed.findings, raw.source or Path(path).name, fmt)


def save(register: RegisterOfInformation, path: str | Path) -> Path:
    """Save as Excel (``.xlsx``) or as a CSV folder (any other path)."""
    p = Path(path)
    if p.suffix.lower() in {".xlsx", ".xlsm"}:
        return write_workbook(register, p)
    return write_csv_folder(register, p)
