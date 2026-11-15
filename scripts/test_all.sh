#!/usr/bin/env bash
# Run every check that works without Flutter: lint + core tests.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m ruff check core
python -m pytest core -q
