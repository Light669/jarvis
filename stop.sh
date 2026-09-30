#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
TOKEN=$(grep -E '^ORCHESTRA_TOKEN=' .env 2>/dev/null | cut -d= -f2-)
PORT=$(PYTHONPATH="$PWD/platform" ${PYTHON:-python3} -c "from orchestra.config import load_config; print(load_config('.').server.port)" 2>/dev/null || echo 8765)
[ -n "$TOKEN" ] && curl -s -X POST -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:$PORT/api/system/shutdown" >/dev/null && sleep 2
for f in data/notifier.pid data/orchestra.pid; do
  if [ -f "$f" ]; then
    pid=$(cat "$f"); kill "$pid" 2>/dev/null
    for i in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -9 "$pid" 2>/dev/null; rm -f "$f"
  fi
done
if command -v docker >/dev/null; then
  ids=$(docker ps -q --filter label=orchestra.sandbox=1 2>/dev/null); [ -n "$ids" ] && docker kill $ids >/dev/null
fi
echo "Orchestra est arrêté."
