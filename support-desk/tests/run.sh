#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob
cd "$(dirname "$0")/.."
echo "== py_compile all functions =="
find functions -name code.py -print0 | xargs -0 python3 -m py_compile
echo "== structural + logic tests =="
for t in tests/test_*.py; do echo "-- $t"; python3 "$t"; done
echo "ALL TESTS PASSED"
