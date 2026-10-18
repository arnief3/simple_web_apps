"""Smoke tests run against every app, at both desktop and phone sizes."""

import json
import re

import pytest
from conftest import APPS, ROOT
from playwright.sync_api import Page


@pytest.mark.parametrize("app", APPS)
def test_loads_without_errors(page: Page, base_url: str, app: str) -> None:
    page.goto(f"{base_url}/{app}/")
    page.wait_for_load_state("load")
    page.wait_for_timeout(300)
    assert page.js_errors == []


@pytest.mark.parametrize("app", APPS)
def test_has_title_and_viewport_meta(page: Page, base_url: str, app: str) -> None:
    page.goto(f"{base_url}/{app}/")
    assert page.title().strip()
    content = page.get_attribute('meta[name="viewport"]', "content") or ""
    assert "width=device-width" in content


@pytest.mark.parametrize("app", APPS)
def test_no_horizontal_scroll(page: Page, base_url: str, app: str) -> None:
    page.goto(f"{base_url}/{app}/")
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0


def test_index_loads_and_links_every_app(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/index.html")
    assert page.js_errors == []
    links = set(page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))"))
    missing = [app for app in APPS if f"{app}/" not in links]
    assert missing == [], f"apps not listed in index.html: {missing}"


@pytest.mark.parametrize("app", APPS)
def test_install_files_present(app: str) -> None:
    """Each app ships a manifest (scoped to its folder) and the icons phones need."""
    folder = ROOT / app
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] and manifest["short_name"]
    assert manifest["start_url"] == manifest["scope"] == "./"
    for icon in manifest["icons"]:
        assert (folder / icon["src"]).is_file(), icon["src"]
    html = (folder / "index.html").read_text(encoding="utf-8")
    for href in ("manifest.json", "icon.svg", "apple-touch-icon.png"):
        assert f'href="{href}"' in html
        assert (folder / href).is_file(), href


def test_storage_keys_are_unique_per_app() -> None:
    """All apps share one localStorage per host, so each app must use its own key prefix."""
    key_re = re.compile(r"localStorage\.(?:get|set|remove)Item\(\s*['\"]([^'\"]+)['\"]")
    owner: dict[str, str] = {}
    for app in APPS:
        for key in set(key_re.findall((ROOT / app / "index.html").read_text(encoding="utf-8"))):
            assert key not in owner, f"storage key {key!r} used by both {owner[key]} and {app}"
            owner[key] = app
