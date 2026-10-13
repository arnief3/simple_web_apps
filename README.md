# Simple Web Apps

Small single-file HTML games and utility apps that run in desktop and phone browsers.
Each app is one self-contained `.html` file at the top level; `index.html` links to all of them.

| App | Type | Description |
| --- | --- | --- |
| [quick-draw-duel.html](quick-draw-duel.html) | Game | Western reaction duel, 2 players on one screen or vs computer |

## Running the apps

- **PC:** open the `.html` file in a browser, or serve the folder (below).
- **Phone (same Wi-Fi):** on the PC run
  `python3 -m http.server 8000 --bind 0.0.0.0` (or the VS Code task *Serve on LAN*),
  then open `http://<pc-ip>:8000` on the phone. Find the IP with `hostname -I`.
  If the phone can't connect, allow port 8000 in the firewall (e.g. `sudo ufw allow 8000/tcp`).

Public hosting (e.g. GitHub Pages) and installing apps on the phone's home screen are not set up yet.

## Adding an app

1. Create `my-app.html` at the top level, following the conventions in [CLAUDE.md](CLAUDE.md).
2. Add it to `index.html` and to the table above.
3. Add `tests/test_my_app.py` with a few interaction checks; `uv run pytest`.
   The shared smoke tests in `tests/test_all_apps.py` pick up the new file automatically.

## Tests

Python is used only for the test harness: pytest + Playwright (Chromium), run at a desktop
size (1280×800) and a phone size (412×915, touch). Tests serve the repo on a local port and
stub all external requests, so they run offline.

Every app is automatically checked for: no JS errors on load, a title and viewport meta,
no horizontal scroll, being linked from `index.html`, and `localStorage` keys not clashing
with other apps.

```bash
uv run pytest            # all tests
uv run ruff check tests  # lint
```

## Setup on a new PC

- **Location:** `~/Documents/Projects/Code/web/simple_web_apps`
  ```bash
  gh repo clone arnief3/simple_web_apps ~/Documents/Projects/Code/web/simple_web_apps
  ```
  (GitHub repo not created yet.)
- **Prerequisites** (beyond `~/dotfiles/NEW_PC.md`): `python3`, `uv`. The setup script
  downloads Playwright's Chromium (~300 MB) into `~/.cache/ms-playwright`. If Chromium can't
  start because of missing system libraries, run
  `sudo .venv/bin/playwright install-deps chromium`.
- **Secrets:** none.
- **Hardware:** none. Any phone on the same Wi-Fi can be used for manual testing.
- **Commands:**
  ```bash
  ./scripts/setup.sh                              # create .venv, install Chromium, run tests
  uv run pytest                                   # test
  python3 -m http.server 8000 --bind 0.0.0.0      # serve to phone/PC
  ```
