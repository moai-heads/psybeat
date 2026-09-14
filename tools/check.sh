#!/usr/bin/env bash
# Smoke test: render and report, fail on non-zero exit.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 src/psybeat.py "$@"
