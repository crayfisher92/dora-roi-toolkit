"""Project files: a workspace saved as a single SQLite database (``.roiproj``).

A project file contains everything needed to continue work later or on another machine:
the raw cell values of all templates (including invalid values still to be fixed), import
findings, the complete audit trail (who changed which field, when, old → new), the version
history, accepted findings with their justifications, and metadata.

Design notes (``docs/DECISIONS.md`` D-043):

* **SQLite** – a single portable file, transactional, readable with standard tools for
  e-discovery or audit, no server.
* **Atomic save** – written to a temporary file in the same directory and then renamed, so a
  crash never leaves a half-written project.
* **Opening untrusted files** – a project received from someone else is treated like any
  upload: size limit, read-only connection, ``trusted_schema=OFF``, integrity check, strict
  format-version and table-type checks, and only plain ``SELECT`` statements.
* Values are stored as JSON with type tags for dates and decimals, so a round trip is exact.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dora_roi import __version__
from dora_roi.io.limits import max_uncompressed_bytes
from dora_roi.io.raw import RawRegister, RawRow, RawTable, RawValue
from dora_roi.validation import Finding
from dora_roi.workspace import Acceptance, Change, Version, Workspace

FORMAT = "dora-roi-toolkit/project"
FORMAT_VERSION = 1
SUFFIX = ".roiproj"

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE tables_ (template TEXT PRIMARY KEY, columns TEXT NOT NULL, source TEXT);
CREATE TABLE rows_ (template TEXT NOT NULL, position INTEGER NOT NULL, row INTEGER,
                    data TEXT NOT NULL, PRIMARY KEY (template, position));
CREATE TABLE import_findings (seq INTEGER PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE changes (seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, template TEXT NOT NULL,
                      row INTEGER NOT NULL, column_ TEXT, old TEXT, new TEXT, at TEXT NOT NULL,
                      user TEXT NOT NULL, note TEXT NOT NULL, row_values TEXT NOT NULL,
                      idx INTEGER NOT NULL);
CREATE TABLE versions (number INTEGER PRIMARY KEY, label TEXT NOT NULL,
                       change_count INTEGER NOT NULL, errors INTEGER NOT NULL,
                       warnings INTEGER NOT NULL, created TEXT NOT NULL, user TEXT NOT NULL);
CREATE TABLE acceptances (key TEXT PRIMARY KEY, rule_id TEXT NOT NULL, reason TEXT NOT NULL,
                          user TEXT NOT NULL, at TEXT NOT NULL);
"""
_TABLES = {"meta", "tables_", "rows_", "import_findings", "changes", "versions",
           "acceptances"}


class ProjectError(ValueError):
    """The file is not a valid project file (or uses an unsupported format version)."""


# --------------------------------------------------------------------------- value codec


def _enc(value: RawValue) -> Any:
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$d": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$dec": str(value)}
    return value


def _dec(value: Any) -> RawValue:
    if isinstance(value, dict):
        if "$dt" in value:
            return datetime.fromisoformat(str(value["$dt"]))
        if "$d" in value:
            return date.fromisoformat(str(value["$d"]))
        if "$dec" in value:
            return Decimal(str(value["$dec"]))
        raise ProjectError(f"unknown value encoding {sorted(value)}")
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise ProjectError(f"unsupported value type {type(value).__name__}")


def _dumps(value: RawValue) -> str:
    return json.dumps(_enc(value), ensure_ascii=False)


def _loads(text: str | None) -> RawValue:
    return None if text is None else _dec(json.loads(text))


# --------------------------------------------------------------------------- save


def save_project(ws: Workspace, path: str | Path) -> Path:
    """Write ``ws`` to ``path`` atomically (temporary file + rename)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".roiproj-", suffix=".tmp", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with ws.lock:
            con = sqlite3.connect(tmp)
            try:
                _write(con, ws)
                con.commit()
            finally:
                con.close()
        tmp.chmod(0o600)  # confidential client data: owner only
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def _write(con: sqlite3.Connection, ws: Workspace) -> None:
    con.executescript(_SCHEMA)
    meta = {
        "format": FORMAT, "format_version": str(FORMAT_VERSION), "toolkit_version": __version__,
        "id": ws.id, "name": ws.name, "source": ws.source or "", "kind": ws.kind,
        "created": ws.created.isoformat(), "saved": datetime.now(UTC).isoformat(),
        "raw_source": ws.raw.source or "", "import_notes": json.dumps(ws.import_notes or []),
    }
    con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    for code, table in ws.raw.tables.items():
        con.execute("INSERT INTO tables_ VALUES (?, ?, ?)",
                    (code, json.dumps(table.columns), table.source))
        con.executemany("INSERT INTO rows_ VALUES (?, ?, ?, ?)", (
            (code, i, r.row, json.dumps({k: _enc(v) for k, v in r.values.items()},
                                        ensure_ascii=False))
            for i, r in enumerate(table.rows)))
    con.executemany("INSERT INTO import_findings (data) VALUES (?)",
                    ((f.model_dump_json(),) for f in ws.raw.findings))
    con.executemany(
        "INSERT INTO changes (kind, template, row, column_, old, new, at, user, note, "
        "row_values, idx) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ((c.kind, c.template, c.row, c.column, _dumps(c.old), _dumps(c.new), c.at.isoformat(),
          c.user, c.note, json.dumps([[k, _enc(v)] for k, v in c.values], ensure_ascii=False),
          c.index) for c in ws.changes))
    con.executemany("INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?)", (
        (v.number, v.label, v.change_count, v.errors, v.warnings, v.created.isoformat(),
         v.user) for v in ws.versions))
    con.executemany("INSERT INTO acceptances VALUES (?, ?, ?, ?, ?)", (
        (a.key, a.rule_id, a.reason, a.user, a.at.isoformat())
        for a in ws.acceptances.values()))


# --------------------------------------------------------------------------- load


def is_project(path: str | Path) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    with p.open("rb") as fh:
        return fh.read(16) == b"SQLite format 3\x00"


def load_project(path: str | Path) -> Workspace:
    """Open a project file. Raises :class:`ProjectError` for anything unexpected."""
    p = Path(path)
    if not is_project(p):
        raise ProjectError("not a project file (expected an SQLite database)")
    if p.stat().st_size > max_uncompressed_bytes():
        raise ProjectError("project file exceeds the size limit")
    uri = f"file:{p.resolve().as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:  # pragma: no cover - sqlite refuses to open
        raise ProjectError(str(exc)) from exc
    try:
        con.execute("PRAGMA trusted_schema = OFF")
        con.execute("PRAGMA cell_size_check = ON")
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ProjectError("project file is corrupted")
        kinds = dict(con.execute("SELECT name, type FROM sqlite_master WHERE name NOT LIKE "
                                 "'sqlite_%' AND type IN ('table', 'view')").fetchall())
        if not set(kinds) >= _TABLES or any(kinds[t] != "table" for t in _TABLES):
            raise ProjectError("not a DORA RoI project file (missing tables)")
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        if meta.get("format") != FORMAT:
            raise ProjectError("not a DORA RoI project file")
        if meta.get("format_version") != str(FORMAT_VERSION):
            raise ProjectError(f"unsupported project format version {meta.get('format_version')}")
        return _read(con, meta)
    except sqlite3.DatabaseError as exc:
        raise ProjectError(f"unreadable project file: {exc}") from exc
    finally:
        con.close()


def _read(con: sqlite3.Connection, meta: dict[str, str]) -> Workspace:
    raw = RawRegister(source=meta.get("raw_source") or None)
    for code, columns, source in con.execute("SELECT template, columns, source FROM tables_"):
        raw.tables[code] = RawTable(code, list(json.loads(columns)), [], source=source)
    for code, row, data in con.execute("SELECT template, row, data FROM rows_ "
                                       "ORDER BY template, position"):
        values = {str(k): _dec(v) for k, v in json.loads(data).items()}
        if code not in raw.tables:
            raise ProjectError(f"row for unknown table {code}")
        raw.tables[code].rows.append(RawRow(row, values))
    raw.findings = [Finding.model_validate_json(d) for (d,) in
                    con.execute("SELECT data FROM import_findings ORDER BY seq")]
    ws = Workspace(meta.get("name", "project"), raw, source=meta.get("source") or None,
                   workspace_id=meta.get("id") or None, kind=meta.get("kind", "project"))
    ws.created = datetime.fromisoformat(meta["created"]) if meta.get("created") else ws.created
    ws.import_notes = json.loads(meta.get("import_notes", "[]")) or None
    ws.changes = [
        Change(kind, template, row, column, _loads(old), _loads(new),
               at=datetime.fromisoformat(at), user=user, note=note,
               values=tuple((str(k), _dec(v)) for k, v in json.loads(row_values)), index=idx)
        for kind, template, row, column, old, new, at, user, note, row_values, idx in
        con.execute("SELECT kind, template, row, column_, old, new, at, user, note, "
                    "row_values, idx FROM changes ORDER BY seq")]
    ws.versions = [
        Version(number, label, change_count, errors, warnings,
                created=datetime.fromisoformat(created), user=user)
        for number, label, change_count, errors, warnings, created, user in
        con.execute("SELECT number, label, change_count, errors, warnings, created, user "
                    "FROM versions ORDER BY number")] or ws.versions
    ws.acceptances = {
        key: Acceptance(key, rule_id, reason, user, datetime.fromisoformat(at))
        for key, rule_id, reason, user, at in
        con.execute("SELECT key, rule_id, reason, user, at FROM acceptances")}
    ws._invalidate()  # acceptances changed after the initial derivation
    return ws


# --------------------------------------------------------------------------- directory


def list_projects(folder: str | Path) -> list[tuple[Path, dict[str, str]]]:
    """Project files in ``folder`` with their metadata (unreadable files are skipped)."""
    out: list[tuple[Path, dict[str, str]]] = []
    for p in sorted(Path(folder).glob(f"*{SUFFIX}")):
        try:
            con = sqlite3.connect(f"file:{p.resolve().as_posix()}?mode=ro", uri=True)
            try:
                meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
            finally:
                con.close()
        except sqlite3.Error:
            continue
        if meta.get("format") == FORMAT:
            out.append((p, meta))
    return out
