# Simple Web Apps

Small HTML games and utility apps that run in desktop and phone browsers.
Each app is one folder with a self-contained `index.html`; the root `index.html` links to all of them.

**Live:** https://arnief3.github.io/simple_web_apps/

| App | Type | Description |
| --- | --- | --- |
| [quick-draw-duel](quick-draw-duel/) | Game | Western reaction duel, 2 players on one screen or vs computer |
| [miles-per-day](miles-per-day/) | Utility | Fastest driving route, split into daily distances |

## Running the apps

- **Hosted:** GitHub Pages redeploys from `main` a minute or so after each push.
- **Install on a phone:** open the app's page, then
  Android Chrome: menu → *Add to Home screen* / *Install app*;
  iPhone Safari: Share → *Add to Home Screen*.
- **Locally on the PC:** `python3 -m http.server 8000` and open `http://localhost:8000`.
- **Locally on a phone (same Wi-Fi):** serve with `--bind 0.0.0.0` (or the VS Code task
  *Serve on LAN*) and open `http://<pc-ip>:8000` (find it with `hostname -I`). Location (GPS)
  needs HTTPS and won't work this way; use the hosted site for that.

## Adding an app

1. Create a folder `my-app/` with `index.html`, `manifest.json` and `icon.svg`, following
   [CLAUDE.md](CLAUDE.md) (copy an existing app's manifest as a starting point).
2. Run `uv run python scripts/make_icons.py` to generate the PNG icons.
3. Add it to the root `index.html` and to the table above.
4. Add `tests/test_my_app.py` and run `uv run pytest`.
   The shared checks in `tests/test_all_apps.py` pick up the new folder automatically.

## Tests

Python is used only for the test harness and icon script: pytest + Playwright (Chromium),
run at a desktop size (1280×800) and a phone size (412×915, touch). Tests serve the repo on
a local port and fake all external requests, so they run offline.

Every app is automatically checked for: no JS errors on load, a title and viewport meta,
no horizontal scroll, being linked from `index.html`, manifest and icon files, and
`localStorage` keys not clashing with other apps.

```bash
uv run pytest                    # all tests
uv run ruff check tests scripts  # lint
```

## Setup on a new PC

- **Location:** `~/Documents/Projects/Code/web/simple_web_apps`
  ```bash
  gh repo clone arnief3/simple_web_apps ~/Documents/Projects/Code/web/simple_web_apps
  ```
- **Prerequisites** (beyond `~/dotfiles/NEW_PC.md`): `python3`, `uv`. The setup script
  downloads Playwright's Chromium (~300 MB) into `~/.cache/ms-playwright`. If Chromium can't
  start because of missing system libraries, run
  `sudo .venv/bin/playwright install-deps chromium`.
- **Secrets:** none. The repo is public, so it must never contain any.
- **Hardware:** none. Any phone can be used for manual testing.
- **Commands:**
  ```bash
  ./scripts/setup.sh                              # create .venv, install Chromium, run tests
  uv run pytest                                   # test
  uv run python scripts/make_icons.py             # regenerate PNG icons after editing an icon.svg
  python3 -m http.server 8000 --bind 0.0.0.0      # serve to phone/PC
  ```
- **Hosting:** GitHub Pages, deploying from branch `main`, folder `/` (repo Settings → Pages).
