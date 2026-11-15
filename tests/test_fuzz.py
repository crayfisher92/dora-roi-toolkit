"""Fuzz tests of the parsers for untrusted files: workbooks, CSV zips, xBRL-CSV packages,
project files and contract inventories.

Each test mutates a valid file – random bit flips, truncation, inserted or overwritten bytes,
and for zip-based formats mutations *inside* archive members so that the XML, CSV and JSON
parsers are reached – and checks the parser's contract: it either returns or raises its own
documented error, never anything else (which would surface as a crash in the CLI or a 500 in
the web app).

``HYPOTHESIS_PROFILE=fuzz`` runs many more examples (scheduled ``fuzz`` workflow).
"""

from __future__ import annotations

import contextlib
import io
import os
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable
from functools import cache
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from dora_roi.inventory import InventoryError, read_inventory
from dora_roi.io.csv_folder import register_to_csv_texts
from dora_roi.io.excel import write_workbook
from dora_roi.io.limits import InputTooLargeError
from dora_roi.io.loader import UnsupportedInputError, load_raw
from dora_roi.io.raw import RawRegister
from dora_roi.io.xbrl_csv import export_xbrl_csv
from dora_roi.project import ProjectError, load_project, save_project
from dora_roi.sample import register_to_raw
from dora_roi.sample.inventory_sample import write_sample_inventory
from dora_roi.workspace import Workspace

from conftest import build_valid_register

FUZZ = os.environ.get("HYPOTHESIS_PROFILE") == "fuzz"
EXAMPLES = 1500 if FUZZ else 25
FUZZ_SETTINGS = settings(max_examples=EXAMPLES, deadline=None, derandomize=not FUZZ,
                         suppress_health_check=[HealthCheck.too_slow,
                                                HealthCheck.data_too_large])

#: What each parser may raise for broken input.
LOAD_ERRORS = (UnsupportedInputError, InputTooLargeError)


# ------------------------------------------------------------------ valid seed files


def _bytes_of(write: Callable[[Path], Path], name: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        return write(Path(tmp) / name).read_bytes()


@cache
def seed_xlsx() -> bytes:
    return _bytes_of(lambda p: write_workbook(build_valid_register(), p), "r.xlsx")


@cache
def seed_csv_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in register_to_csv_texts(build_valid_register()).items():
            zf.writestr(name, text)
    return buf.getvalue()


@cache
def seed_xbrl() -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        return export_xbrl_csv(build_valid_register(), tmp).path.read_bytes()


@cache
def seed_project() -> bytes:
    raw: RawRegister = register_to_raw(build_valid_register())
    return _bytes_of(lambda p: save_project(Workspace("fuzz", raw), p), "p.roiproj")


@cache
def seed_inventory() -> bytes:
    return _bytes_of(write_sample_inventory, "inventory.xlsx")


# ------------------------------------------------------------------ mutations


@st.composite
def byte_mutations(draw: st.DrawFn, seed: bytes) -> bytes:
    data = bytearray(seed)
    for _ in range(draw(st.integers(1, 6))):
        if not data:
            break
        pos = draw(st.integers(0, len(data) - 1))
        op = draw(st.sampled_from(["flip", "truncate", "insert", "overwrite"]))
        if op == "flip":
            data[pos] ^= 1 << draw(st.integers(0, 7))
        elif op == "truncate":
            del data[pos:]
        elif op == "insert":
            data[pos:pos] = draw(st.binary(min_size=1, max_size=64))
        else:
            chunk = draw(st.binary(min_size=1, max_size=64))
            data[pos:pos + len(chunk)] = chunk
    return bytes(data)


@st.composite
def member_mutations(draw: st.DrawFn, seed: bytes) -> bytes:
    """Re-pack the zip with some members' contents (or names) mutated."""
    with zipfile.ZipFile(io.BytesIO(seed)) as zf:
        members = [(info.filename, zf.read(info)) for info in zf.infolist()]
    for _ in range(draw(st.integers(1, 3))):
        i = draw(st.integers(0, len(members) - 1))
        name, content = members[i]
        if draw(st.booleans()):
            content = draw(byte_mutations(content)) if content else draw(st.binary(max_size=64))
        else:
            content = draw(st.sampled_from([b"", b"\xff\xfe\x00", b"<x>&undefined;</x>",
                                            b'{"a": [1, 2', b"\x00" * 16, b"a,b\n1"]))
        if draw(st.integers(0, 9)) == 0:
            name = draw(st.sampled_from([name.upper(), "../" + name, name + "/", "x.csv"]))
        members[i] = (name, content)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members:
            zf.writestr(name, content)
    return buf.getvalue()


def zip_inputs(seed: Callable[[], bytes]) -> st.SearchStrategy[bytes]:
    return st.one_of(byte_mutations(seed()), member_mutations(seed()))


def _write(data: bytes, name: str) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / name
    path.write_bytes(data)
    return tmp, path


def assert_contract(load: Callable[[Path], object], data: bytes, name: str,
                    allowed: tuple[type[BaseException], ...]) -> None:
    tmp, path = _write(data, name)
    try:
        load(path)
    except allowed:
        pass
    finally:
        tmp.cleanup()


# ------------------------------------------------------------------ the parsers


@FUZZ_SETTINGS
@given(zip_inputs(seed_xlsx))
def test_workbook_reader(data: bytes) -> None:
    assert_contract(load_raw, data, "register.xlsx", LOAD_ERRORS)


@FUZZ_SETTINGS
@given(zip_inputs(seed_csv_zip))
def test_csv_zip_reader(data: bytes) -> None:
    assert_contract(load_raw, data, "register.zip", LOAD_ERRORS)


@FUZZ_SETTINGS
@given(zip_inputs(seed_xbrl))
def test_xbrl_package_reader(data: bytes) -> None:
    assert_contract(load_raw, data, "package.zip", LOAD_ERRORS)


@FUZZ_SETTINGS
@given(zip_inputs(seed_inventory))
def test_inventory_reader(data: bytes) -> None:
    assert_contract(read_inventory, data, "inventory.xlsx",
                    (InventoryError, InputTooLargeError))


@FUZZ_SETTINGS
@given(byte_mutations(seed_project()))
def test_project_file_bytes(data: bytes) -> None:
    assert_contract(load_project, data, "fuzz.roiproj", (ProjectError,))


@FUZZ_SETTINGS
@given(st.sampled_from(["rows_", "meta", "changes", "versions", "acceptances",
                        "import_findings", "tables_"]),
       st.one_of(st.text(max_size=40), st.binary(max_size=40), st.integers(), st.none(),
                 st.sampled_from(['{"t": "date", "v": "2025-13-45"}', '{"t": "decimal"}',
                                  "[1, 2", '{"c0010": {"t": "x"}}', "9" * 400])))
def test_project_file_values(table: str, value: object) -> None:
    """Valid SQLite, tampered content: every column of one table set to a hostile value."""
    tmp, path = _write(seed_project(), "fuzz.roiproj")
    try:
        con = sqlite3.connect(path)
        try:
            columns = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            for column in columns:
                try:
                    con.execute(f"UPDATE {table} SET {column} = ?", (value,))
                except (sqlite3.IntegrityError, OverflowError):
                    continue  # the hostile value cannot be stored in that column
            con.commit()
        finally:
            con.close()
        with contextlib.suppress(ProjectError):
            load_project(path)
    finally:
        tmp.cleanup()


def test_regressions_found_by_fuzzing(tmp_path: Path) -> None:
    """Inputs the long fuzz run once crashed on, kept as fixed examples."""
    bad_csv = io.BytesIO()
    with zipfile.ZipFile(bad_csv, "w") as zf:  # csv.Error: new-line character in a field
        zf.writestr("b_01.01.csv", "c0010,c0020\nab\rcd,x\n")
    path = tmp_path / "register.zip"
    path.write_bytes(bad_csv.getvalue())
    with contextlib.suppress(*LOAD_ERRORS):
        load_raw(path)
    broken = bytearray(seed_project())
    broken[100:4096] = b"\x80" * (4096 - 100)  # corrupt first page: undecodable check output
    project = tmp_path / "broken.roiproj"
    project.write_bytes(bytes(broken))
    with contextlib.suppress(ProjectError):
        load_project(project)
