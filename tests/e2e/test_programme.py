"""End-to-end tests of the DORA programme screens (Art. 30 contracts, incidents, FINMA,
dashboard): flows, WCAG 2.2 AA (axe-core, light and dark) and reflow at 360 px."""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = pytest.mark.e2e


def open_sample(page: Any, label: str = "Sample with 25 deliberate errors") -> str:
    page.goto("/")
    page.get_by_role("button", name=label).click()
    page.wait_for_url(re.compile(r"/w/[0-9a-f]+"))
    return str(page.url).split("?")[0].rstrip("/")


PROGRAMME_PAGES = ["/contracts", "/contracts/checklist", "/contract/AR-DE-0057",
                   "/contract/CO-LU-0002", "/incidents", "/incidents/new",
                   "/incidents/INC-2025-006", "/finma"]
STANDALONE_REPORTS = ["/contracts/plan.html", "/incidents/summary.html"]


def test_contract_assessment_with_document_suggestions(page: Any) -> None:
    url = open_sample(page)
    page.get_by_role("link", name="Art. 30 contracts").click()
    page.wait_for_url(url + "/contracts")
    page.get_by_role("link", name="AR-DE-0057").click()
    page.wait_for_url(re.compile(r"/contract/AR-DE-0057$"))
    assert page.get_by_role("heading", name=re.compile("AR-DE-0057")).is_visible()
    page.get_by_role("button", name="Use the sample contract").click()
    page.wait_for_selector("#draft-banner")
    assert page.get_by_text("Suggestions – not saved yet.").is_visible()
    tlpt = page.locator("fieldset.provision").filter(has_text="threat-led penetration testing")
    assert tlpt.get_by_text("Suggestion: not found").is_visible()
    tlpt.get_by_label("Present").check()
    page.fill("#ev-30_3_d", "TLPT clause agreed in side letter 2025-12")
    page.get_by_role("button", name="Save assessment").click()
    page.wait_for_url(re.compile(r"saved=1"))
    assert page.get_by_text("Assessment saved").is_visible()
    assert page.locator("#ev-30_3_d").input_value().startswith("TLPT clause agreed")
    assert page.get_by_text(re.compile(r"30\.3\.d: missing → present")).is_visible()
    page.goto(url + "/register/B_02.01?q=AR-DE-0057")
    link = page.locator(".register-table a.pill").first
    assert link.inner_text().startswith("Gaps")
    link.click()
    page.wait_for_url(re.compile(r"/contract/AR-DE-0057$"))


def test_contracts_filter_and_checklist(page: Any) -> None:
    url = open_sample(page, "Clean sample")
    page.goto(url + "/contracts")
    page.select_option("#c-status", "compliant")
    page.get_by_role("button", name="Filter", exact=True).click()
    page.wait_for_url(re.compile(r"status=compliant"))
    rows = page.locator(".contracts-table tbody tr")
    assert rows.count() == 2
    page.get_by_role("link", name="Open checklist").click()
    assert page.get_by_role("heading", name="Art. 30 checklist").is_visible()


def test_incident_classification_and_countdown(page: Any) -> None:
    url = open_sample(page)
    page.get_by_role("link", name="Incidents", exact=True).click()
    page.wait_for_url(url + "/incidents")
    assert page.get_by_text("kronos-certificate-rotation").first.is_visible()
    major = page.locator(".incident-table tbody tr").first
    assert major.get_by_text("Major").is_visible()
    clock = major.locator("time.countdown")
    assert clock.inner_text().startswith("in ")
    page.get_by_role("link", name="+ New incident").click()
    page.wait_for_url(re.compile(r"/incidents/new$"))
    page.fill("#title", "Card authorisation outage")
    page.fill("#detected_at", "2025-12-01T09:00")
    page.locator("#q-critical_services").get_by_label("Yes", exact=True).check()
    page.locator("#q-malicious_access").get_by_label("No", exact=True).check()
    page.fill("#a-downtime_hours", "3")
    page.get_by_label("DE Germany").check()
    page.get_by_label("LU Luxembourg").check()
    page.get_by_role("button", name="Save and classify").click()
    page.wait_for_url(re.compile(r"/incidents/INC-\d{4}-\d{3}\?saved=1"))
    result = page.locator(".result-card")
    assert result.get_by_text("Major", exact=True).is_visible()
    assert page.get_by_role("heading", name="Reporting to the competent authority").is_visible()
    assert page.locator(".deadline").count() == 3
    page.get_by_role("button", name="Record Initial notification as submitted").click()
    page.wait_for_url(re.compile(r"saved=1"))
    assert page.get_by_text("Submitted on time").first.is_visible() or \
        page.get_by_text("Submitted late").first.is_visible()


def test_countdown_updates_without_reload(page: Any) -> None:
    url = open_sample(page)
    page.goto(url + "/incidents")
    page.evaluate("""() => {
      const el = document.querySelector('time.countdown');
      el.setAttribute('datetime', new Date(Date.now() - 2 * 3600e3).toISOString());
    }""")
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.wait_for_function(
        "document.querySelector('time.countdown').textContent.startsWith('overdue by')",
        timeout=5000)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_programme_accessibility_wcag22_aa(browser: Any, base_url: str, a11y: Any,
                                           scheme: str) -> None:
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, base_url=base_url,
                              color_scheme=scheme)
    pg = ctx.new_page()
    url = open_sample(pg)
    problems = []
    for suffix in PROGRAMME_PAGES + STANDALONE_REPORTS + ["/contracts?lang=de"]:
        pg.goto(url + suffix)
        found = a11y(pg)
        if found:
            problems.append(f"{suffix}:\n{found}")
    pg.goto(url + "/incidents?lang=en")
    major = pg.locator("a", has_text=re.compile(r"INC-20\d\d-014")).first
    major_url = url + "/incidents/" + major.inner_text().strip()
    pg.goto(major_url)
    found = a11y(pg)
    if found:
        problems.append(f"major incident:\n{found}")
    pg.goto(url + "/contract/AR-DE-0057?lang=en")
    pg.get_by_role("button", name="Use the sample contract").click()
    pg.wait_for_selector("#draft-banner")
    found = a11y(pg)
    if found:
        problems.append(f"suggestion draft:\n{found}")
    ctx.close()
    assert not problems, "\n\n".join(problems)


def test_programme_reflow_360(browser: Any, base_url: str) -> None:
    ctx = browser.new_context(viewport={"width": 360, "height": 800}, base_url=base_url)
    pg = ctx.new_page()
    url = open_sample(pg)
    for suffix in PROGRAMME_PAGES:
        pg.goto(url + suffix)
        overflow = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{suffix}: page scrolls horizontally by {overflow}px"
    ctx.close()
