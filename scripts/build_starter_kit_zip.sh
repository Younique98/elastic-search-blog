#!/usr/bin/env bash
# Rebuilds static/starter-kit.zip from starter-kit/ — the actual file
# STARTER_KIT_FILE_URL points buyers at. Run this after any change to
# starter-kit/ and commit the resulting zip alongside your change; it's
# not built automatically at deploy time, the same way static/style.css
# isn't built from a source file either.
set -euo pipefail

cd "$(dirname "$0")/.."

rm -f static/starter-kit.zip
zip -r static/starter-kit.zip starter-kit \
  -x '*__pycache__*' \
  -x '*.pytest_cache*' \
  -x '*/.env' \
  -x '*.pyc'

echo "Built static/starter-kit.zip ($(du -h static/starter-kit.zip | cut -f1))"
