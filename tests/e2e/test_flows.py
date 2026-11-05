"""End-to-end tests of the main workbench flows in a real browser."""

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


def test_overview_shows_score_and_stepper(page: Any) -> None:
    url = open_sample(page)
    assert page.locator("#score-meter").get_attribute("value") == "97"
    assert page.get_by_text("Not ready for submission").first.is_visible()
    steps = page.locator(".stepper li")
    assert steps.count() == 4
    page.get_by_role("link", name="Fix 27 blocking error(s)").click()
    page.wait_for_url(url + "/fix")
    assert page.locator('[aria-current="step"]').inner_text().strip().endswith("Fix") or \
        "Fix" in page.locator('[aria-current="step"]').inner_text()


def test_inline_fix_revalidates_without_reload(page: Any) -> None:
    url = open_sample(page)
    page.goto(url + "/fix?template=B_02.02")
    item = page.locator("[data-finding]").filter(has=page.locator('input[value="UK"]'))
    assert item.count() == 1
    item.get_by_role("button", name=re.compile("Use suggestion")).click()
    assert item.locator('input[name="value"]').input_value() == "GB"
    page.evaluate("window.__marker = 1")  # survives only if there is no reload
    item.get_by_role("button", name="Save").click()
    page.wait_for_selector("[data-finding].fixed")
    assert page.evaluate("window.__marker") == 1
    assert page.locator('[data-bind="errors"]').first.inner_text() == "26"
    # the live region is cleared and refilled after a short delay so that screen readers
    # announce repeated messages; wait for the announcement instead of reading it at once
    page.wait_for_function(
        "document.getElementById('live').textContent.includes('26 error(s)')", timeout=5000)


def test_register_search_and_row_edit(page: Any) -> None:
    url = open_sample(page, "Clean sample")
    page.goto(url + "/register/B_05.01?q=nimbus")
    rows = page.locator(".register-table tbody tr")
    assert rows.count() == 2
    rows.first.get_by_role("link", name=re.compile("Edit")).click()
    page.wait_for_url(re.compile(r"/register/B_05\.01/\d+$"))
    page.fill("#f-c0050", "Nimbus Cloud Inc. (renamed)")
    page.get_by_role("button", name="Save row").click()
    page.wait_for_url(re.compile(r"saved=1"))
    assert page.locator("#f-c0050").input_value() == "Nimbus Cloud Inc. (renamed)"


def test_mapping_wizard(page: Any) -> None:
    page.goto("/map")
    page.get_by_role("button", name=re.compile("sample inventory")).click()
    page.wait_for_url(re.compile(r"/map/[0-9a-f]+$"))
    assert page.locator("#col0").input_value() == "contract_ref"
    assert page.locator("#col14").input_value() == ""
    page.get_by_role("button", name="Continue").click()
    page.fill("#lei", "3912RO6DCAXX71K9W972")
    page.fill("#name", "Alpenrand Bank (Europe) AG")
    page.fill("#competent_authority", "BaFin")
    page.fill("#reporting_date", "2025-12-31")
    page.get_by_role("button", name="Continue").click()
    page.wait_for_url(re.compile(r"/preview$"))
    assert page.locator("table.preview tbody tr").count() == 8
    page.get_by_role("button", name="Create workspace").click()
    page.wait_for_url(re.compile(r"/w/[0-9a-f]+$"))
    assert page.get_by_text("inventory rows imported").is_visible()


def test_graph_to_provider_page(page: Any) -> None:
    url = open_sample(page, "Clean sample")
    page.goto(url + "/analyse")
    node = page.locator('svg.dep-graph a.node[aria-label^="Nimbus Cloud Services EMEA"]')
    node.focus()
    assert page.locator("svg.dep-graph.focusing").count() == 1
    node.click()
    page.wait_for_url(re.compile(r"/provider/"))
    assert page.get_by_role("heading", name="Nimbus Cloud Services EMEA Ltd").is_visible()
    assert page.get_by_text(re.compile("Subcontractor in")).is_visible()


def test_compare_last_year(page: Any) -> None:
    page.goto("/")
    page.get_by_role("button", name="Sample: last year vs this year").click()
    page.wait_for_url(re.compile(r"/compare\?other="))
    assert page.get_by_text("Legacy Mainframe Services GmbH").first.is_visible()


def test_german_and_dark_mode(page: Any) -> None:
    page.goto("/?lang=de")
    assert page.locator("html").get_attribute("lang") == "de"
    assert page.get_by_role("heading", name="Arbeitsbereich für ein Register anlegen").is_visible()
    page.get_by_role("button", name="Dunkel").click()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.get_by_role("button", name="System").click()
    assert page.locator("html").get_attribute("data-theme") is None


def test_keyboard_skip_link(page: Any) -> None:
    page.goto("/")
    page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement.className")
    assert "skip-link" in focused
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main"


def test_responsive_no_horizontal_scroll(browser: Any, base_url: str) -> None:
    ctx = browser.new_context(viewport={"width": 360, "height": 800}, base_url=base_url)
    pg = ctx.new_page()
    url = open_sample(pg)
    for suffix in ("", "/fix", "/analyse", "/export"):
        pg.goto(url + suffix)
        overflow = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{suffix}: page scrolls horizontally by {overflow}px"
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_accessibility_wcag22_aa(browser: Any, base_url: str, a11y: Any, scheme: str) -> None:
    # bypass_csp only so that axe-core can be injected; the app itself runs under its CSP
    # in every other test
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, base_url=base_url,
                              color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    url = open_sample(pg)
    pg.goto(url + "/register/B_05.01")
    code = re.search(r"/provider/([^\"]+)\"", pg.content())
    pages = ["/", url, url + "/fix?template=B_02.02", url + "/register/B_02.02",
             url + "/register/B_02.02/4", url + "/analyse", url + "/export",
             url + "/compare?version=1", url + "/versions", url + "/audit", "/map",
             "/?lang=de"]
    if code:
        pages.append(url + "/provider/" + code.group(1))
    problems = []
    for target in pages:
        pg.goto(target)
        found = a11y(pg)
        if found:
            problems.append(f"{target}:\n{found}")
    ctx.close()
    assert not problems, "\n\n".join(problems)


def test_no_csp_violations(page: Any) -> None:
    violations: list[str] = []
    page.on("console", lambda m: violations.append(m.text)
            if "Content Security Policy" in m.text or "Refused to" in m.text else None)
    url = open_sample(page)
    for suffix in ("", "/fix?template=B_02.02", "/analyse", "/audit"):
        page.goto(url + suffix)
    assert not violations, violations


def test_accept_finding_and_audit_trail(page: Any) -> None:
    url = open_sample(page, "Clean sample")
    page.goto(url)
    page.fill("#user-name", "Lena Berger")
    page.get_by_role("button", name="Save name").click()
    page.goto(url + "/fix?template=B_01.02")
    page.get_by_text("Accept with justification").first.click()
    page.get_by_label("Justification").first.fill("Holding is outside the DORA scope")
    page.get_by_role("button", name="Accept finding").first.click()
    page.wait_for_url(re.compile("/fix"))
    assert page.get_by_text("Holding is outside the DORA scope").is_visible()
    assert page.locator("#score-meter").get_attribute("value") == "100"
    page.goto(url + "/audit")
    assert page.get_by_text("Finding accepted").is_visible()
    assert page.get_by_role("cell", name="Lena Berger").first.is_visible()
