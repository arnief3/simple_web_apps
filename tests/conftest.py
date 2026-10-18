"""Shared fixtures: a local HTTP server for the repo and Playwright pages at PC/phone sizes."""

import functools
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent

# Every top-level folder with an index.html is an app (the root index.html is the launcher).
APPS = sorted(p.parent.name for p in ROOT.glob("*/index.html") if not p.parent.name.startswith("."))

VIEWPORTS = {
    "desktop": {"viewport": {"width": 1280, "height": 800}},
    "phone": {
        "viewport": {"width": 412, "height": 915},
        "device_scale_factor": 2.6,
        "is_mobile": True,
        "has_touch": True,
    },
}


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture(params=list(VIEWPORTS), ids=list(VIEWPORTS))
def page(request: pytest.FixtureRequest, browser: Browser, base_url: str) -> Iterator[Page]:
    """A fresh page per test; collects uncaught JS errors in ``page.js_errors``."""
    context = browser.new_context(**VIEWPORTS[request.param])
    pg = context.new_page()

    # Keep tests offline and deterministic: answer external requests (CDNs, fonts) with
    # an empty response so apps must not depend on them to work.
    def stub_external(route):
        if route.request.url.startswith(base_url):
            route.continue_()
        else:
            route.fulfill(status=200, body="")

    pg.route("**/*", stub_external)

    errors: list[str] = []
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    pg.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    pg.js_errors = errors  # type: ignore[attr-defined]

    yield pg
    context.close()
