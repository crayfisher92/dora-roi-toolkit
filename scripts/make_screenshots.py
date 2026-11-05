"""Generate the README screenshots (docs/screenshots/*.png) from the running app.

    python scripts/make_screenshots.py            # needs Playwright + Chromium

Screenshots are taken at device scale factor 2 with the Alpenrand sample data, in light mode
(and one in dark mode), so they can be regenerated after every UI change.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from dora_roi.web.devserver import BackgroundServer

OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ and Path("/opt/pw-browsers").exists():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/pw-browsers"


def sample(page: Page, label: str) -> str:
    page.goto("/")
    page.get_by_role("button", name=label).click()
    page.wait_for_url(re.compile(r"/w/[0-9a-f]+"))
    return page.url.split("?")[0].rstrip("/")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with BackgroundServer() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:  # Playwright's own build missing: use a pre-installed Chromium
            browser = p.chromium.launch(executable_path=os.environ.get(
                "CHROMIUM_EXECUTABLE", "/opt/pw-browsers/chromium"))
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2,
                                  base_url=base, color_scheme="light")
        page = ctx.new_page()
        page.goto("/")
        page.screenshot(path=str(OUT / "01-home.png"))
        url = sample(page, "Sample with 25 deliberate errors")
        page.screenshot(path=str(OUT / "02-overview.png"))
        page.goto(url + "/fix?template=B_02.02")
        item = page.locator("[data-finding]").filter(has=page.locator('input[value="UK"]'))
        item.scroll_into_view_if_needed()
        item.get_by_role("button", name=re.compile("Use suggestion")).click()
        page.evaluate("el => el.scrollIntoView({block: 'center'})",
                      item.element_handle())
        page.screenshot(path=str(OUT / "03-fix.png"))
        page.goto(url + "/register/B_02.02")
        page.screenshot(path=str(OUT / "04-register.png"))
        page.goto(url + "/analyse?color=region")
        page.locator("#h-graph").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "05-graph.png"))
        page.goto(url + "/register/B_05.01?q=Nimbus+Cloud+Services")
        page.locator(".register-table tbody a[href*='/provider/']").first.click()
        page.wait_for_url(re.compile("/provider/"))
        page.screenshot(path=str(OUT / "06-provider.png"))
        page.goto("/map")
        page.get_by_role("button", name=re.compile("sample inventory")).click()
        page.wait_for_url(re.compile(r"/map/[0-9a-f]+$"))
        page.screenshot(path=str(OUT / "07-mapping.png"))
        page.goto("/")
        page.get_by_role("button", name="Sample: last year vs this year").click()
        page.wait_for_url(re.compile("/compare"))
        page.screenshot(path=str(OUT / "08-compare.png"))
        dark = browser.new_context(viewport={"width": 1280, "height": 800}, device_scale_factor=2,
                                   base_url=base, color_scheme="dark")
        dpage = dark.new_page()
        url = sample(dpage, "Sample with 25 deliberate errors")
        dpage.goto(url + "/fix?template=B_02.02&lang=de")
        ditem = dpage.locator("[data-finding]").filter(has=dpage.locator('input[value="UK"]'))
        dpage.evaluate("el => el.scrollIntoView({block: 'center'})", ditem.element_handle())
        dpage.screenshot(path=str(OUT / "09-fix-dark-de.png"))
        # DORA programme screens
        url = sample(page, "Sample with 25 deliberate errors")
        page.goto(url + "/dashboard")
        page.locator("main h2").first.scroll_into_view_if_needed()
        page.evaluate("window.scrollTo(0, document.querySelector('main').offsetTop - 8)")
        page.screenshot(path=str(OUT / "10-dashboard.png"))
        page.goto(url + "/contracts?critical=1")
        page.evaluate("window.scrollTo(0, document.querySelector('main').offsetTop - 8)")
        page.screenshot(path=str(OUT / "11-contracts.png"))
        page.goto(url + "/contract/AR-DE-0057")
        page.get_by_role("button", name="Use the sample contract").click()
        page.wait_for_selector("#draft-banner")
        tlpt = page.locator("fieldset.provision").filter(has_text="threat-led penetration")
        page.evaluate("el => el.scrollIntoView({block: 'start'})", tlpt.element_handle())
        page.screenshot(path=str(OUT / "12-assessment.png"))
        page.goto(url + "/incidents")
        page.locator(".incident-table a").first.click()
        page.wait_for_url(re.compile(r"/incidents/INC-"))
        page.evaluate("window.scrollTo(0, document.querySelector('main').offsetTop - 8)")
        page.screenshot(path=str(OUT / "13-incident.png"))
        page.goto(url + "/finma")
        page.evaluate("window.scrollTo(0, document.querySelector('main').offsetTop - 8)")
        page.screenshot(path=str(OUT / "14-finma.png"))
        browser.close()
    for f in sorted(OUT.glob("*.png")):
        print(f"wrote {f.relative_to(OUT.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
