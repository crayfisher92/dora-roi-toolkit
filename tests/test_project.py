"""SQLite project files (save / load / autosave)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from dora_roi.cli import main
from dora_roi.io.loader import InputFormat, detect_format, load
from dora_roi.project import (
    FORMAT_VERSION,
    ProjectError,
    is_project,
    list_projects,
    load_project,
    save_project,
)
from dora_roi.sample import generate_sample, register_to_raw
from dora_roi.web.app import create_app
from dora_roi.workspace import Workspace

from conftest import build_valid_register


def _busy_workspace() -> Workspace:
    ws = Workspace("Alpenrand", register_to_raw(generate_sample().source_register))
    row = ws.table("B_02.02").rows[3].row or 0
    ws.edit("B_02.02", row, "c0120", "AT", user="Lena")
    ws.add_row("B_06.01", {"c0010": "F-X", "c0070": date(2025, 1, 1),
                           "c0080": Decimal("4.5")}, user="Lena")
    ws.delete_row("B_02.02", ws.table("B_02.02").rows[0].row or 0, user="Thomas")
    info = next(f for f in ws.report.findings if f.rule_id == "XRF-014")
    ws.accept(info, "Holding outside the DORA scope", user="Lena")
    ws.import_notes = ["note"]
    return ws


def test_roundtrip_is_exact(tmp_path: Path) -> None:
    ws = _busy_workspace()
    path = save_project(ws, tmp_path / "sub" / "a.roiproj")
    assert is_project(path) and (path.stat().st_mode & 0o777) == 0o600
    back = load_project(path)
    assert back.id == ws.id and back.name == ws.name and back.import_notes == ["note"]
    assert back.register.model_dump() == ws.register.model_dump()
    assert back.report.severity_counts() == ws.report.severity_counts()
    assert [(c.kind, c.user, c.old, c.new) for c in back.changes] == \
        [(c.kind, c.user, c.old, c.new) for c in ws.changes]
    assert [(v.number, v.change_count) for v in back.versions] == \
        [(v.number, v.change_count) for v in ws.versions]
    assert back.acceptances.keys() == ws.acceptances.keys()
    assert back.register_at(1).model_dump() == ws.register_at(1).model_dump()
    row = next(r for r in back.table("B_06.01").rows if r.values.get("c0010") == "F-X")
    assert row.values["c0070"] == date(2025, 1, 1) and row.values["c0080"] == Decimal("4.5")
    assert not list(tmp_path.glob("sub/.roiproj-*"))  # no temp file left behind


def test_save_overwrites_atomically(tmp_path: Path) -> None:
    ws = Workspace("x", register_to_raw(build_valid_register()))
    p = save_project(ws, tmp_path / "x.roiproj")
    ws.edit("B_02.01", 4, "c0050", "1")
    save_project(ws, p)
    assert load_project(p).row("B_02.01", 4).values["c0050"] == "1"


def _corrupt(path: Path, sql: str) -> Path:
    con = sqlite3.connect(path)
    con.executescript(sql)
    con.commit()
    con.close()
    return path


@pytest.mark.parametrize(("sql", "message"), [
    ("UPDATE meta SET value='other' WHERE key='format'", "not a DORA RoI project"),
    (f"UPDATE meta SET value='{FORMAT_VERSION + 1}' WHERE key='format_version'",
     "unsupported project format version"),
    ("DROP TABLE acceptances; CREATE VIEW acceptances AS SELECT 1 AS key", "missing tables"),
    ("DROP TABLE changes", "missing tables"),
    ("UPDATE rows_ SET data='{\"c0010\": {\"$evil\": 1}}' WHERE position=0 "
     "AND template='B_02.01'", "unknown value encoding"),
    ("UPDATE rows_ SET template='B_99.99' WHERE position=0 AND template='B_02.01'",
     "unknown table"),
])
def test_rejects_tampered_files(tmp_path: Path, sql: str, message: str) -> None:
    p = save_project(Workspace("x", register_to_raw(build_valid_register())),
                     tmp_path / "x.roiproj")
    _corrupt(p, sql)
    with pytest.raises(ProjectError, match=message):
        load_project(p)


def test_rejects_non_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    txt = tmp_path / "x.roiproj"
    txt.write_text("not sqlite")
    with pytest.raises(ProjectError, match="not a project file"):
        load_project(txt)
    assert not is_project(tmp_path / "missing.roiproj")
    other = tmp_path / "other.roiproj"
    _corrupt(other, "CREATE TABLE t(x)")
    with pytest.raises(ProjectError):
        load_project(other)
    good = save_project(Workspace("x", register_to_raw(build_valid_register())),
                        tmp_path / "g.roiproj")
    monkeypatch.setenv("ROI_MAX_UNCOMPRESSED_MB", "0")
    with pytest.raises(ProjectError, match="size limit"):
        load_project(good)
    monkeypatch.delenv("ROI_MAX_UNCOMPRESSED_MB")
    broken = tmp_path / "broken.roiproj"
    data = bytearray(good.read_bytes())
    data[200:4000] = b"\xff" * 3800
    broken.write_bytes(bytes(data))
    with pytest.raises(ProjectError):
        load_project(broken)


def test_list_projects_skips_foreign_files(tmp_path: Path) -> None:
    save_project(Workspace("Client A", register_to_raw(build_valid_register())),
                 tmp_path / "a.roiproj")
    (tmp_path / "junk.roiproj").write_text("x")
    _corrupt(tmp_path / "foreign.roiproj", "CREATE TABLE meta(key, value)")
    names = [m["name"] for _, m in list_projects(tmp_path)]
    assert names == ["Client A"]


def test_cli_accepts_project_files(tmp_path: Path) -> None:
    p = save_project(_busy_workspace(), tmp_path / "a.roiproj")
    assert detect_format(p) is InputFormat.PROJECT
    loaded = load(p)
    assert loaded.input_format is InputFormat.PROJECT and loaded.register.b_02_02
    res = CliRunner().invoke(main, ["validate", str(p), "--fail-on", "never"])
    assert res.exit_code == 0 and "error(s)" in res.output


def test_web_save_and_open_project(tmp_path: Path) -> None:
    client = TestClient(create_app())
    url = client.post("/sample", data={"variant": "dirty"}, follow_redirects=False
                      ).headers["location"]
    client.post(url + "/cell", data={"template": "B_02.01", "row": "4", "column": "c0050",
                                     "value": "42"})
    assert "Project file" in client.get(url + "/export").text
    data = client.get(url + "/download/project").content
    assert data[:16] == b"SQLite format 3\x00"
    other = TestClient(create_app())
    r = other.post("/project/open", files={"file": ("client.roiproj", data)},
                   follow_redirects=False)
    assert r.status_code == 303
    new_url = r.headers["location"]
    assert new_url != url  # fresh id, not the one stored in the file
    page = other.get(new_url + "/audit").text
    assert "Value changed" in page
    r = other.post("/project/open", files={"file": ("x.roiproj", b"garbage")})
    assert r.status_code == 400 and "not a project file" in r.text
    r = other.post("/project/open", files={"file": ("x.xlsx", b"garbage")})
    assert r.status_code == 400


def test_projects_folder_autosave_and_reopen(tmp_path: Path) -> None:
    app = create_app(projects_dir=tmp_path)
    client = TestClient(app)
    home = client.get("/").text
    assert "Saved projects" in home and "No saved projects" in home
    url = client.post("/sample", data={"variant": "clean"}, follow_redirects=False
                      ).headers["location"]
    files = list(tmp_path.glob("*.roiproj"))
    assert len(files) == 1 and files[0].name.startswith("Alpenrand-clean-")
    client.post(url + "/cell", data={"template": "B_02.01", "row": "4", "column": "c0050",
                                     "value": "777"})
    assert load_project(files[0]).row("B_02.01", 4).values["c0050"] == "777"  # autosaved
    other = TestClient(app)
    home = other.get("/").text
    assert files[0].name in home
    r = other.post("/projects/open", data={"file": files[0].name}, follow_redirects=False)
    assert r.status_code == 303
    reopened = r.headers["location"]
    other.post(reopened + "/cell", data={"template": "B_02.01", "row": "4",
                                         "column": "c0050", "value": "888"})
    assert len(list(tmp_path.glob("*.roiproj"))) == 1  # same file updated
    assert "Autosaved after every change" in other.get(reopened + "/export").text
    assert other.post("/projects/open", data={"file": "../etc/passwd"}).status_code == 404
    assert TestClient(create_app()).post("/projects/open",
                                         data={"file": files[0].name}).status_code == 404


def test_cli_audit_log(tmp_path: Path) -> None:
    p = save_project(_busy_workspace(), tmp_path / "a.roiproj")
    out = tmp_path / "audit.csv"
    res = CliRunner().invoke(main, ["audit-log", str(p), "-o", str(out)])
    assert res.exit_code == 0
    lines = out.read_text().splitlines()
    assert lines[0].startswith("timestamp_utc,user,action")
    assert any(",Lena,set,B_02.02," in ln for ln in lines)
    assert any(",Thomas,delete," in ln for ln in lines)
    bad = tmp_path / "bad.roiproj"
    bad.write_text("x")
    assert CliRunner().invoke(main, ["audit-log", str(bad)]).exit_code == 2
