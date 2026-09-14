#!/usr/bin/env bash
# Convenience wrapper: render, then commit everything with the given message.
# Usage: tools/commit.sh "bass: tighten envelope"
set -euo pipefail
cd "$(dirname "$0")/.."
msg="${1:?usage: tools/commit.sh \"<commit message>\"}"
python3 src/psybeat.py >/dev/null
git add -A
git commit -m "$msg"
