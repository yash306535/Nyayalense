"""Automated accessibility checks on every view, state and theme.

Automated testing catches a fraction of what matters. What it does catch, it
catches every time, so this suite is set to zero tolerance and the manual
screen-reader checklist in ACCESSIBILITY.md records what it does not cover.
"""

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Page

pytestmark = pytest.mark.e2e

AXE = Axe()

RULESETS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]


def check(page: Page, label: str) -> None:
    """Fail the test on any axe violation, naming what and where."""
    results = AXE.run(page, options={"runOnly": RULESETS})
    violations = results.response["violations"]
    if violations:
        report = "\n".join(
            f"  [{entry['impact']}] {entry['id']}: {entry['help']}\n"
            f"    {'; '.join(node['target'][0] for node in entry['nodes'][:4])}"
            for entry in violations
        )
        pytest.fail(f"{label} has {len(violations)} accessibility violations:\n{report}")


@pytest.fixture(params=["light", "dark"])
def themed(request: pytest.FixtureRequest, browser: Browser, base_url: str) -> Page:
    """A page in one colour scheme, with the rental sample loaded."""
    context = browser.new_context(
        color_scheme=request.param, viewport={"width": 1280, "height": 900}
    )
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    yield page
    context.close()


def test_the_upload_view_is_accessible(themed: Page) -> None:
    check(themed, "upload")


def test_the_loading_state_is_accessible(themed: Page) -> None:
    themed.click('[data-sample="leave-licence-v1"]')
    themed.wait_for_selector("#workspace:not([hidden])", timeout=40_000)
    check(themed, "loading")


def test_the_overview_is_accessible(themed: Page) -> None:
    themed.click('[data-sample="leave-licence-v1"]')
    themed.wait_for_selector(".seal", timeout=40_000)
    check(themed, "overview")


def test_the_review_is_accessible(themed: Page) -> None:
    themed.click('[data-sample="leave-licence-v1"]')
    themed.wait_for_selector(".seal", timeout=40_000)
    themed.click('[data-tab="review"]')
    themed.wait_for_selector(".risk", timeout=40_000)
    check(themed, "review")


def test_an_answer_and_a_not_found_are_accessible(themed: Page) -> None:
    themed.click('[data-sample="leave-licence-v1"]')
    themed.wait_for_selector(".seal", timeout=40_000)
    themed.click('[data-tab="ask"]')

    themed.fill("#question-input", "How much is the security deposit?")
    themed.click('#tabpanel button[type="submit"]')
    themed.wait_for_selector("#answers .panel", timeout=40_000)

    themed.fill("#question-input", "Who won the cricket match yesterday?")
    themed.click('#tabpanel button[type="submit"]')
    themed.wait_for_timeout(1500)
    check(themed, "answers")


def test_the_comparison_table_is_accessible(themed: Page) -> None:
    themed.click('[data-sample="leave-licence-v1"]')
    themed.wait_for_selector(".seal", timeout=40_000)
    themed.click('[data-tab="compare"]')
    themed.select_option("#compare-other", "leave-licence-v2")
    themed.click("#view-check .card button:has-text('Compare')")
    themed.wait_for_selector(".ctable", timeout=60_000)
    check(themed, "comparison table")


def test_the_brief_is_accessible(themed: Page) -> None:
    themed.click('[data-sample="leave-licence-v1"]')
    themed.wait_for_selector(".seal", timeout=40_000)
    themed.click('[data-tab="brief"]')
    themed.wait_for_selector("#brief", timeout=40_000)
    check(themed, "brief")


def test_the_law_lookup_and_its_table_are_accessible(themed: Page) -> None:
    themed.click('a[data-route="laws"]')
    themed.wait_for_selector("#law-search")
    check(themed, "law lookup, empty")

    themed.fill("#law-search", "IPC 420")
    themed.click('#view-laws button[type="submit"]')
    themed.wait_for_selector("#law-results table", timeout=30_000)
    check(themed, "law comparison table")


def test_the_help_directory_is_accessible(themed: Page) -> None:
    themed.click('a[data-route="help"]')
    themed.wait_for_selector("#help-pane .register li", timeout=30_000)
    check(themed, "help")


def test_the_drafting_form_is_accessible(themed: Page) -> None:
    themed.click('a[data-route="draft"]')
    themed.wait_for_selector("#template-select", timeout=30_000)
    themed.select_option("#template-select", "deposit_refund_request")
    themed.wait_for_selector("#draft-preview > *", timeout=30_000)
    check(themed, "drafting")


def test_the_about_page_is_accessible(themed: Page) -> None:
    themed.click('a[href="#/about"]')
    themed.wait_for_selector("#about-pane .card", timeout=30_000)
    check(themed, "about")


def test_the_clause_dialog_is_accessible(browser: Browser, base_url: str) -> None:
    """On a phone a citation opens its clause in a dialog."""
    context = browser.new_context(viewport={"width": 380, "height": 760})
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.click('[data-sample="leave-licence-v1"]')
    page.wait_for_selector(".seal", timeout=40_000)
    page.locator(".seal").first.click()
    page.wait_for_selector("dialog[open]", timeout=10_000)
    check(page, "clause dialog")
    context.close()


def test_the_error_state_is_accessible(browser: Browser, base_url: str) -> None:
    context = browser.new_context()
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.route("**/api/v1/samples/**", lambda route: route.fulfill(status=500, body="{}"))
    page.click('[data-sample="leave-licence-v1"]')
    page.wait_for_selector(".notice--error", timeout=20_000)
    check(page, "error")
    context.close()


@pytest.mark.parametrize("width", [320, 360, 768])
def test_narrow_screens_reflow_without_horizontal_scrolling(
    browser: Browser, base_url: str, width: int
) -> None:
    """WCAG 2.2 reflow: usable at 320 CSS pixels with no sideways scrolling."""
    context = browser.new_context(viewport={"width": width, "height": 760})
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.click('[data-sample="leave-licence-v1"]')
    page.wait_for_selector(".seal", timeout=40_000)

    check(page, f"overview at {width}px")
    overflows = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
    )
    assert not overflows, f"the page scrolls sideways at {width}px"
    context.close()


def test_text_survives_being_enlarged_to_200_percent(browser: Browser, base_url: str) -> None:
    """WCAG 1.4.4. Injecting a style tag is blocked by the page's own policy,
    which is the correct behaviour, so the enlargement is appended to a real
    same-origin stylesheet instead.
    """
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()

    def enlarge(route: object) -> None:
        response = route.fetch()
        route.fulfill(
            response=response,
            body=response.text() + "\nhtml { font-size: 200% !important; }",
            headers={**response.headers, "content-type": "text/css"},
        )

    page.route("**/css/base.css", enlarge)
    page.goto(base_url, wait_until="networkidle")

    scaled = page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")
    assert scaled >= 30, "the enlargement did not take effect"

    page.click('[data-sample="leave-licence-v1"]')
    page.wait_for_selector(".seal", timeout=40_000)

    overflows = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
    )
    assert not overflows, "the page scrolls sideways at 200% text size"
    context.close()
