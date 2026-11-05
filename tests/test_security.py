"""Security tests referenced by the threat model in docs/SECURITY.md."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from dora_roi.analytics import analyse
from dora_roi.graph import build_graph, render_svg
from dora_roi.io.csv_folder import register_to_csv_texts
from dora_roi.io.loader import load
from dora_roi.reporting import render_html
from dora_roi.reporting.charts import Bar, Segment, column_chart, hbar_chart, segmented_bar
from dora_roi.reporting.executive import render_executive_summary
from dora_roi.sample import register_to_raw
from dora_roi.validation import validate
from dora_roi.web.app import create_app
from dora_roi.workspace import Workspace

from conftest import build_valid_register

PAYLOAD = '"><script>alert(1)</script><img src=x onerror=alert(2)>'


def _evil_register():  # type: ignore[no-untyped-def]
    reg = build_valid_register()
    reg.b_05_01[0].legal_name = PAYLOAD
    reg.b_05_01[1].legal_name = PAYLOAD + "sub"
    reg.b_06_01[0].function_name = PAYLOAD
    reg.b_01_01[0].name = PAYLOAD
    reg.b_02_02[0].governing_law_country = PAYLOAD  # becomes a finding message/value
    return reg


def _assert_escaped(html: str) -> None:
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror" not in html


def test_xss_charts_and_graph() -> None:
    _assert_escaped(str(hbar_chart([Bar(PAYLOAD, 1, PAYLOAD, PAYLOAD)], title=PAYLOAD)))
    _assert_escaped(str(column_chart([Bar(PAYLOAD, 1, PAYLOAD)], title=PAYLOAD)))
    _assert_escaped(str(segmented_bar([Segment(PAYLOAD, 1, PAYLOAD, PAYLOAD)], title=PAYLOAD)))
    reg = _evil_register()
    _assert_escaped(str(render_svg(build_graph(reg), link_prefix="/p/", labels={
        "title": PAYLOAD, "critical": PAYLOAD})))


def test_xss_reports() -> None:
    reg = _evil_register()
    report = validate(reg)
    _assert_escaped(render_html(report))
    _assert_escaped(render_executive_summary(reg, report, analysis=analyse(reg),
                                             client_name=PAYLOAD))


def test_xss_web_pages() -> None:
    app = create_app()
    client = TestClient(app)
    ws = Workspace(PAYLOAD, register_to_raw(_evil_register()))
    client.get("/")  # obtain a session cookie
    ws.owner = client.cookies["roi_session"]
    app.state.workspaces.add(ws.id, ws)
    base = f"/w/{ws.id}"
    pages = ["", "/fix", "/fix?template=B_02.02", "/register/B_05.01", "/register/B_05.01/4",
             "/analyse", "/analyse?color=region", "/audit", "/versions", "/renewals",
             "/compare?version=1", f"/provider/{ws.register.b_05_01[0].provider_code}"]
    for p in pages:
        r = client.get(base + p)
        assert r.status_code == 200, p
        _assert_escaped(r.text)


def test_zip_slip_member_names_are_ignored(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in register_to_csv_texts(build_valid_register()).items():
            zf.writestr(f"../../../../tmp/evil/{name}", text)
        zf.writestr("../../evil.sh", "rm -rf /")
    zpath = tmp_path / "slip.zip"
    zpath.write_bytes(buf.getvalue())
    before = set(Path("/tmp").glob("evil*"))
    loaded = load(zpath)
    assert len(loaded.register.b_02_02) == 1  # members recognised by base name only
    assert set(Path("/tmp").glob("evil*")) == before  # nothing extracted to disk
    client = TestClient(create_app())
    r = client.post("/import", files={"file": ("../../x.zip", zpath.read_bytes())},
                    follow_redirects=False)
    assert r.status_code == 303


def test_wizard_ignores_client_file_name(tmp_path: Path) -> None:
    client = TestClient(create_app())
    data = b"Supplier;Ref\nAcme;C1\n"
    r = client.post("/map", files={"file": ("../../../etc/passwd.csv", data)},
                    follow_redirects=False)
    assert r.status_code == 303


def test_serve_disables_access_log(monkeypatch: object) -> None:
    import uvicorn
    from click.testing import CliRunner

    from dora_roi import cli

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))  # type: ignore[attr-defined]
    assert CliRunner().invoke(cli.main, ["serve", "--port", "8123"]).exit_code == 0
    assert calls[-1]["access_log"] is False and calls[-1]["server_header"] is False
    assert calls[-1]["host"] == "127.0.0.1"
    CliRunner().invoke(cli.main, ["serve", "--access-log"])
    assert calls[-1]["access_log"] is True


def test_no_outbound_network_code() -> None:
    root = Path(__file__).resolve().parent.parent / "src" / "dora_roi"
    forbidden = ("import requests", "import httpx", "urllib.request", "http.client",
                 "smtplib", "ftplib", "urlopen(")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} uses {token}"
