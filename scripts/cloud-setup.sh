#!/usr/bin/env bash
# SessionStart hook for Claude Code cloud sessions: make sure .venv exists with
# requirements-dev.txt installed. Does nothing outside cloud sessions, and is safe to
# re-run: it skips pip when the requirements haven't changed since the last install.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/..}"

if [ ! -x .venv/bin/python ]; then
  if python3 -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' 2>/dev/null; then
    python3 -m venv .venv
  else
    # Cloud images may ship a different Python; use a uv-managed 3.12 instead.
    uv python install 3.12
    uv venv --seed --python 3.12 .venv
  fi
fi

stamp=.venv/.requirements.sha256
current=$(cat requirements.txt requirements-dev.txt | sha256sum | cut -d' ' -f1)
if [ "$(cat "$stamp" 2>/dev/null)" != "$current" ]; then
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt
  echo "$current" > "$stamp"
fi

echo "project-tracker: .venv ready ($(.venv/bin/python --version))"
