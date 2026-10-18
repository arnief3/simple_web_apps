"""Basic interaction checks for quick-draw-duel."""

from playwright.sync_api import Page, expect


def _open(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/quick-draw-duel/")
    expect(page.locator("#menu")).to_be_visible()


def test_start_vs_computer_hides_menu(page: Page, base_url: str) -> None:
    _open(page, base_url)
    page.click("#bcpu")
    expect(page.locator("#menu")).to_have_class("hidden")
    expect(page.locator("#h2 .name")).to_have_text("You")
    expect(page.locator("#h2 .msg")).to_have_text("Steady…")
    assert page.js_errors == []


def test_firing_early_gives_point_to_opponent(page: Page, base_url: str) -> None:
    _open(page, base_url)
    page.click("#b2p")
    page.wait_for_timeout(400)  # past the 300 ms input lock, well before the earliest DRAW (1.8 s)
    page.keyboard.press("a")  # Player 1 fires early
    expect(page.locator("#h1 .msg")).to_have_text("Too early!")
    expect(page.locator("#h2 .msg")).to_have_text("Win!")
    expect(page.locator("#h2 .bullets .b.on")).to_have_count(1)
    assert page.js_errors == []


def test_target_selector_sets_bullet_count(page: Page, base_url: str) -> None:
    _open(page, base_url)
    page.click('.seg[data-t="5"]')
    page.click("#b2p")
    expect(page.locator("#h1 .bullets .b")).to_have_count(5)
