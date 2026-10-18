"""Render each app's icon.svg to the PNG icons phones need (iOS ignores SVG home-screen icons).

Run after editing an icon:  uv run python scripts/make_icons.py
Writes icon-192.png, icon-512.png (transparent) and apple-touch-icon.png (180px, filled with the
manifest's theme_color because iOS shows transparent corners as black).
"""

import base64
import json
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SIZES = {"icon-192.png": 192, "icon-512.png": 512, "apple-touch-icon.png": 180}


def render(page: Page, svg: bytes, size: int, background: str | None, out: Path) -> None:
    src = "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
    bg = background or "transparent"
    page.set_viewport_size({"width": size, "height": size})
    page.set_content(
        f'<body style="margin:0;background:{bg}">'
        f'<img src="{src}" width="{size}" height="{size}" style="display:block"></body>'
    )
    page.wait_for_function("document.images[0].complete")
    page.screenshot(path=str(out), omit_background=background is None)


def main() -> None:
    apps = sorted(p.parent for p in ROOT.glob("*/icon.svg"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        for app in apps:
            svg = (app / "icon.svg").read_bytes()
            theme = json.loads((app / "manifest.json").read_text())["theme_color"]
            for name, size in SIZES.items():
                bg = theme if name == "apple-touch-icon.png" else None
                render(page, svg, size, bg, app / name)
            print(f"{app.name}: {', '.join(SIZES)}")
        browser.close()


if __name__ == "__main__":
    main()
