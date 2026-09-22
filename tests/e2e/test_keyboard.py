"""The main flow, without ever touching a pointer."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

MAX_TABS = 60


def tab_to(page: Page, selector: str) -> None:
    """Press Tab until the element matching ``selector`` has focus."""
    for _ in range(MAX_TABS):
        if page.evaluate(f"document.activeElement?.matches({selector!r}) ?? false"):
            return
        page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement?.outerHTML?.slice(0, 120)")
    pytest.fail(f"never reached {selector}; focus stopped at {focused}")


def test_the_skip_link_is_the_first_stop_and_works(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.keyboard.press("Tab")
    expect(page.locator(".skip-link")).to_be_focused()
    expect(page.locator(".skip-link")).to_be_visible()

    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement?.id || location.hash") in {"main", "#main"}


def test_a_sample_can_be_loaded_with_the_keyboard(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    tab_to(page, '[data-sample="leave-licence-v1"]')
    page.keyboard.press("Enter")
    page.wait_for_selector(".seal", timeout=40_000)
    expect(page.locator("#clause-list .clause").first).to_be_visible()


def test_the_tabs_follow_the_aria_pattern(loaded: Page) -> None:
    """Roving tabindex, arrow keys, Home and End, as the pattern requires."""
    tabs = loaded.locator('[role="tab"]')
    first = tabs.first
    first.focus()
    expect(first).to_have_attribute("tabindex", "0")

    loaded.keyboard.press("ArrowRight")
    expect(tabs.nth(1)).to_be_focused()
    expect(tabs.nth(1)).to_have_attribute("aria-selected", "true")
    expect(first).to_have_attribute("tabindex", "-1")

    loaded.keyboard.press("End")
    expect(tabs.last).to_be_focused()

    loaded.keyboard.press("Home")
    expect(tabs.first).to_be_focused()

    loaded.keyboard.press("ArrowLeft")
    expect(tabs.last).to_be_focused()


def test_a_citation_can_be_activated_with_the_keyboard(loaded: Page) -> None:
    seal = loaded.locator(".seal").first
    seal.focus()
    loaded.keyboard.press("Enter")

    expect(loaded.locator(".clause--active")).to_have_count(1)
    focused = loaded.evaluate("document.activeElement?.className || ''")
    assert "clause" in focused


def test_a_question_can_be_asked_with_the_keyboard(loaded: Page) -> None:
    loaded.locator('[data-tab="ask"]').click()
    field = loaded.locator("#question-input")
    field.focus()
    field.type("How much is the security deposit?")
    loaded.keyboard.press("Enter")
    loaded.wait_for_selector("#answers .panel", timeout=40_000)
    expect(loaded.locator("#answers .panel").first).to_be_visible()


def test_keyboard_focus_shows_a_visible_ring(loaded: Page) -> None:
    """A ring drawn only on pointer focus would help nobody, so tab to it."""
    tab_to(loaded, '[role="tab"]')
    outline = loaded.evaluate(
        """() => {
          const style = getComputedStyle(document.activeElement);
          return { width: style.outlineWidth, style: style.outlineStyle };
        }""",
    )
    assert outline["style"] != "none"
    assert outline["width"] != "0px"


def test_no_element_is_removed_from_the_tab_order_without_reason(loaded: Page) -> None:
    """A roving tabindex on the tab list is the one legitimate exception."""
    offenders = loaded.evaluate(
        """() => [...document.querySelectorAll('button, a[href], input, select, textarea')]
            .filter((node) => node.tabIndex < 0 && !node.disabled
                              && node.offsetParent !== null
                              && node.getAttribute('role') !== 'tab')
            .map((node) => node.outerHTML.slice(0, 80))""",
    )
    assert offenders == []


def test_targets_are_large_enough_to_hit(loaded: Page) -> None:
    """WCAG 2.2 target size (minimum) is 24 by 24 CSS pixels."""
    small = loaded.evaluate(
        """() => [...document.querySelectorAll('button, a[href], select')]
            .filter((node) => node.offsetParent !== null)
            .map((node) => ({ html: node.outerHTML.slice(0, 70), rect: node.getBoundingClientRect() }))
            .filter(({ rect }) => rect.width > 0 && (rect.width < 24 || rect.height < 24))
            .map(({ html }) => html)""",
    )
    assert small == []
