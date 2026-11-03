#!/bin/bash
# Setup helper: index each archive as soon as its download finishes. Stops when downloads are done
# and one more pass finds nothing new. Usage: scripts/index_loop.sh [embed-backend]
cd "$(dirname "$0")/.."
EMBED="${1:-local}"
while :; do
  .venv/bin/python -m app.index --embed "$EMBED"
  if ! pgrep -f "scripts/fetch.py" >/dev/null; then
    .venv/bin/python -m app.index --embed "$EMBED"     # final pass for the last download
    echo "INDEX LOOP DONE"; exit 0
  fi
  sleep 60
done
