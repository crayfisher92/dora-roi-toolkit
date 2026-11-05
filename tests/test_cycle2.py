"""Regression tests for BACKLOG cycle 2 (B-18 … B-24)."""

from __future__ import annotations

import dataclasses
from datetime import date

from fastapi.testclient import TestClient

from dora_roi.analytics import analyse
from dora_roi.analytics.impact import failure_impact
from dora_roi.analytics.renewals import NoticeStatus, notice_schedule
from dora_roi.quality import Readiness
from dora_roi.reporting import render_html, render_markdown
from dora_roi.sample import generate_sample, register_to_raw
from dora_roi.validation import RULES
from dora_roi.web.app import create_app
from dora_roi.workspace import Workspace

from conftest import build_valid_register


def test_sessions_are_isolated() -> None:
    app = create_app()
    alice, bob = TestClient(app), TestClient(app)
    r = alice.post("/sample", data={"variant": "clean"}, follow_redirects=False)
    url = r.headers["location"]
    wid = url.split("/w/")[1]
    assert "roi_session" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    assert "samesite=strict" in r.headers["set-cookie"].lower()
    assert alice.get(url).status_code == 200
    assert wid not in bob.get("/").text
    for path in ("", "/fix", "/download/xlsx", "/audit"):
        assert bob.get(url + path).status_code == 404, path
    assert bob.get("/api" + url).status_code == 404
    assert bob.post(url + "/cell", data={"template": "B_02.01", "row": "4", "column": "c0050",
                                        "value": "1"}).status_code == 404
    wiz = alice.post("/map", data={"use_sample": "1"}, follow_redirects=False)
    assert bob.get(wiz.headers["location"]).status_code == 404
    forged = TestClient(app, cookies={"roi_session": "short"})
    assert forged.get(url).status_code == 404  # invalid cookie -> new session


def test_rule_failure_blocks_readiness() -> None:
    rule = RULES["BUS-001"]

    def boom(ctx: object) -> list[object]:
        raise RuntimeError("bug")

    RULES["BUS-001"] = dataclasses.replace(rule, check=boom)  # type: ignore[arg-type]
    try:
        ws = Workspace("x", register_to_raw(build_valid_register()))
        assert ws.report.rule_failures and ws.quality.readiness is Readiness.NOT_READY
        assert "Validation incomplete" in render_html(ws.report)
        app = create_app()
        c = TestClient(app)
        url = c.post("/sample", data={"variant": "clean"}, follow_redirects=False
                     ).headers["location"]
        assert "Validation incomplete" in c.get(url).text
    finally:
        RULES["BUS-001"] = rule


def test_notice_schedule() -> None:
    reg = generate_sample(inject_errors=False).register
    items = notice_schedule(reg)
    assert items == sorted(items, key=lambda i: (i.deadline, i.contract_ref))
    first = items[0]
    assert first.contract_ref == "AR-DE-0105" and first.status is NoticeStatus.DUE_90
    assert first.deadline == date(2026, 1, 14) and first.critical
    assert all(i.end_date > date(2025, 12, 31) for i in items)
    late = notice_schedule(reg, date(2026, 2, 1))
    assert any(i.status is NoticeStatus.PASSED for i in late)
    assert any(i.status is NoticeStatus.LATER for i in items)
    a = analyse(reg)
    assert a.notice_due_critical == 2
    assert any("notice deadline" in k.title for k in a.key_findings)


def test_renewals_page_and_access_log_flag() -> None:
    c = TestClient(create_app())
    url = c.post("/sample", data={"variant": "clean"}, follow_redirects=False).headers["location"]
    page = c.get(url + "/renewals").text
    assert "Notice deadlines" in page and "AR-DE-0105" in page and "Due in 14 days" in page
    crit = c.get(url + "/renewals?critical=1").text
    assert crit.count("<tr>") <= page.count("<tr>")
    assert "Kündigungsstichtag" in c.get(url + "/renewals?lang=de").text


def test_accepted_findings_in_reports_and_orphans_pruned() -> None:
    ws = Workspace("s", register_to_raw(generate_sample(inject_errors=False).source_register))
    info = next(f for f in ws.report.findings if f.rule_id == "XRF-014")
    ws.accept(info, "Holding outside scope")
    md = render_markdown(ws.report)
    assert "## Accepted findings" in md and "Holding outside scope" in md
    assert "Accepted findings" in render_html(ws.report)
    de = next(r for r in ws.table("B_01.02").rows if r.values.get("c0060"))
    assert de.row is not None
    ws.edit("B_01.02", de.row, "c0060", "")  # parent removed -> finding disappears
    assert ws.report.accepted == [] and ws.acceptances == {}
    assert ws.changes[-1].kind == "unaccept" and "expired" in ws.changes[-1].note


def test_impact_reports_exit_plans() -> None:
    reg = generate_sample().register  # with injected missing exit plans
    flagged = []
    for p in reg.b_05_01:
        fi = failure_impact(reg, p.provider_code or "")
        flagged += [f for f in fi.functions if f.exit_plan is False]
    assert flagged
    assert any(f.exit_plan is None for p in reg.b_05_01
               for f in failure_impact(reg, p.provider_code or "").functions)
