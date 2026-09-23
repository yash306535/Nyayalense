"""The flow a user actually takes, in a real browser."""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_the_page_loads_in_demo_mode(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    expect(page).to_have_title("NyayaLens — Understand what you sign, with proof")
    expect(page.locator("#demo-badge")).to_be_visible()
    expect(page.locator("#check-heading")).to_contain_text("Check a document")


def test_the_disclaimer_is_on_every_view(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    for route in ("check", "laws", "draft", "help"):
        page.click(f'a[data-route="{route}"]')
        expect(page.locator(".app-footer")).to_contain_text("isn't legal advice")


def test_a_sample_loads_and_is_explained(loaded: Page) -> None:
    expect(loaded.locator("#clause-list .clause").first).to_be_visible()
    assert loaded.locator("#clause-list .clause").count() > 20
    expect(loaded.locator(".trust").first).to_contain_text("verified against your document")


def test_every_statement_shows_the_clause_behind_it(loaded: Page) -> None:
    """The product's promise, seen from the browser."""
    statements = loaded.locator("#tabpanel .statement")
    assert statements.count() > 0
    for index in range(statements.count()):
        expect(statements.nth(index).locator(".seal")).to_have_count(1, timeout=5_000)


def test_activating_a_citation_shows_and_focuses_the_clause(loaded: Page) -> None:
    loaded.locator(".seal").first.click()
    expect(loaded.locator(".clause--active")).to_have_count(1)
    expect(loaded.locator("mark").first).to_be_visible()

    focused_class = loaded.evaluate("document.activeElement?.className || ''")
    assert "clause" in focused_class, "focus must land on the clause, not stay behind"
    expect(loaded.locator("text=Back to the answer")).to_be_visible()


def test_the_review_flags_risks_with_words_not_only_colour(loaded: Page) -> None:
    loaded.click('[data-tab="review"]')
    loaded.wait_for_selector(".risk", timeout=40_000)
    badge = loaded.locator(".badge--high, .badge--medium, .badge--low").first
    expect(badge).to_contain_text("impact")


def test_the_deliberate_amount_mismatch_is_reported(loaded: Page) -> None:
    loaded.click('[data-tab="review"]')
    loaded.wait_for_selector(".risk", timeout=40_000)
    expect(loaded.locator("text=An amount is written two different ways")).to_be_visible()


def test_a_question_the_document_answers(loaded: Page) -> None:
    loaded.click('[data-tab="ask"]')
    loaded.fill("#question-input", "How much is the security deposit?")
    loaded.click('#tabpanel button[type="submit"]')
    loaded.wait_for_selector("#answers .panel", timeout=40_000)
    expect(loaded.locator("#answers .seal").first).to_be_visible()


def test_a_question_the_document_does_not_answer(loaded: Page) -> None:
    """The state that separates this from a general assistant."""
    loaded.click('[data-tab="ask"]')
    loaded.fill("#question-input", "Who won the cricket match yesterday?")
    loaded.click('#tabpanel button[type="submit"]')
    loaded.wait_for_selector("#answers .panel", timeout=40_000)

    answer = loaded.locator("#answers .panel").first
    expect(answer).to_contain_text("This document doesn't say")
    expect(answer.locator(".seal")).to_have_count(0)
    expect(answer).to_contain_text("You could ask the other party")


def test_comparing_two_versions_produces_one_table(loaded: Page) -> None:
    loaded.click('[data-tab="compare"]')
    loaded.select_option("#compare-other", "leave-licence-v2")
    loaded.click("#view-check .card button:has-text('Compare')")
    loaded.wait_for_selector(".ctable", timeout=90_000)

    table = loaded.locator(".ctable").first
    expect(table.locator("caption")).to_be_visible()
    expect(table.locator('thead th[scope="col"]').first).to_be_visible()
    expect(table.locator('tbody th[scope="row"]').first).to_be_visible()


def test_the_comparison_table_is_reachable_by_keyboard(loaded: Page) -> None:
    loaded.click('[data-tab="compare"]')
    loaded.select_option("#compare-other", "leave-licence-v2")
    loaded.click("#view-check .card button:has-text('Compare')")
    loaded.wait_for_selector(".table-wrap", timeout=90_000)
    expect(loaded.locator(".table-wrap").first).to_have_attribute("tabindex", "0")
    expect(loaded.locator(".table-wrap").first).to_have_attribute("role", "region")


def test_the_brief_gathers_what_was_verified(loaded: Page) -> None:
    loaded.click('[data-tab="brief"]')
    loaded.wait_for_selector("#brief", timeout=40_000)
    expect(loaded.locator("#brief")).to_contain_text("Information, not legal advice")


def test_clearing_the_document_returns_to_the_start(loaded: Page) -> None:
    loaded.once("dialog", lambda dialog: dialog.accept())
    loaded.click("text=Clear this document")
    expect(loaded.locator("#upload-panel")).to_be_visible()
    expect(loaded.locator("#workspace")).to_be_hidden()


def test_switching_language_translates_the_interface(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.select_option("#language-select", "mr")
    expect(page.locator("html")).to_have_attribute("lang", "mr")
    expect(page.locator('a[data-route="help"]')).to_contain_text("मदत")


def test_the_theme_can_be_switched(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="networkidle")
    page.click("#theme-toggle")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle")).to_have_attribute("aria-pressed", "true")


def test_the_glossary_prefers_the_documents_own_definition(loaded: Page) -> None:
    glossary = loaded.locator("#tabpanel details").first
    expect(glossary).to_be_visible()
    glossary.click()
    expect(glossary.locator("dt").first).to_be_visible()
    # The rental sample defines Premises, Licensor and Licensee for itself.
    expect(glossary).to_contain_text("Defined in this document")


def test_a_what_if_reports_only_what_the_document_says(loaded: Page) -> None:
    loaded.click('[data-tab="scenarios"]')
    loaded.locator("#tabpanel .row button").first.click()
    loaded.wait_for_selector("#tabpanel article.panel", timeout=40_000)

    result = loaded.locator("#tabpanel article.panel")
    expect(result.locator(".trust")).to_be_visible()
    expect(result).to_contain_text("What you could do next")


def test_a_what_if_the_document_does_not_cover(loaded: Page) -> None:
    loaded.click('[data-tab="scenarios"]')
    loaded.fill("#scenario-input", "A meteorite lands on the roof")
    loaded.click('#tabpanel button[type="submit"]')
    loaded.wait_for_selector("#tabpanel article.panel", timeout=40_000)
    expect(loaded.locator("#tabpanel article.panel")).to_contain_text("does not describe")


def test_the_reading_level_can_be_changed(loaded: Page) -> None:
    expect(loaded.locator("#level-simple")).to_be_checked()
    loaded.click('label[for="level-detailed"]')
    expect(loaded.locator("#level-detailed")).to_be_checked()
    loaded.wait_for_selector(".seal", timeout=40_000)
    expect(loaded.locator(".seal").first).to_be_visible()


def test_the_comparison_marks_changes_without_relying_on_colour(loaded: Page) -> None:
    loaded.click('[data-tab="compare"]')
    loaded.select_option("#compare-other", "leave-licence-v2")
    loaded.click("#view-check .card button:has-text('Compare')")
    loaded.wait_for_selector(".ctable ins", timeout=90_000)

    inserted = loaded.locator(".ctable ins").first
    deleted = loaded.locator(".ctable del").first
    expect(inserted).to_be_visible()
    expect(deleted).to_be_visible()

    # Each carries visually hidden wording, so the change is not colour alone.
    expect(inserted.locator(".sr-only")).to_have_count(1)
    expect(deleted.locator(".sr-only")).to_have_count(1)
    assert inserted.locator(".sr-only").inner_text().strip()
