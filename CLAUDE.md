# Simple Web Apps: project conventions

Collection of small HTML games and utility apps for desktop and phone browsers.

## Structure
- One self-contained `.html` file per app at the top level (inline CSS + JS). Only split into
  extra files for a compelling reason (large media → `assets/<app>/`; code shared by many apps).
- Every app is linked from `index.html` and listed in the README table.
- Python (`uv`, pytest, Playwright) is only for tests. No build step, no npm.

## Every app must
- Have `<meta name="viewport" content="width=device-width,initial-scale=1">` and a `<title>`.
  Games may add `maximum-scale=1,user-scalable=no`; utility apps keep zoom enabled.
- Work with mouse, touch and (where sensible) keyboard: use pointer events, not separate
  mouse/touch handlers; nothing that only works on hover.
- Fit phone screens: no horizontal scroll, use `dvh` instead of `vh` for full height,
  respect `env(safe-area-inset-*)`, tap targets ≥ 44px.
- Prefix every `localStorage` key with a short app-specific prefix (e.g. `qd_`), and wrap
  storage access in try/catch.
- Work offline: external resources (Google Fonts, CDN scripts with pinned versions) are
  optional extras with fallbacks, never required.
- Support light/dark (`prefers-color-scheme`) for utility apps; games may use their own theme.

## Tests
- `tests/test_all_apps.py` checks every app automatically (desktop + phone viewport).
- Each app gets `tests/test_<app>.py` with a few interaction checks.
- Run `uv run pytest` and `uv run ruff check tests` after changes.

## Not decided yet
- Public hosting (GitHub Pages) and PWA/home-screen install: don't add manifests or service
  workers until decided.
