#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load environment variables for launchd/non-interactive shells.
if [ -f ".env" ]; then
  set -a
  source ".env"
  set +a
fi

# Activate virtual environment when available, otherwise use system Python.
if [ -x "./venv/bin/python" ]; then
  PYTHON_BIN="./venv/bin/python"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" src/main.py --once
