#!/usr/bin/env bash
# One-step dev setup: checks tools, creates .venv with test deps, installs Chromium for Playwright.
# Safe to run repeatedly.
set -euo pipefail

cd "$(dirname "$0")/.."

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: '$1' not found. $2" >&2
    exit 1
  fi
}

need python3 "Install Python 3 (used to serve the apps locally)."
need uv "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"

echo "==> Creating/updating .venv from uv.lock"
uv sync

echo "==> Installing Playwright Chromium (skipped if already present)"
if ! uv run playwright install chromium; then
  echo "Chromium install failed. If system libraries are missing, run:" >&2
  echo "  sudo $(pwd)/.venv/bin/playwright install-deps chromium" >&2
  exit 1
fi

echo "==> Running tests"
uv run pytest -q

cat <<'EOF'

Setup complete.
  Serve on LAN:  python3 -m http.server 8000 --bind 0.0.0.0
                 then open http://<this-pc-ip>:8000 on your phone (same Wi-Fi)
  Run tests:     uv run pytest
  Lint:          uv run ruff check tests
EOF
