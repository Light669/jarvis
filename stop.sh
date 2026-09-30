#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
TOKEN=$(grep -E '^ORCHESTRA_TOKEN=' .env 2>/dev/null | cut -d= -f2-)
[ -n "$TOKEN" ] && curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/api/system/shutdown >/dev/null && sleep 1
for f in data/notifier.pid data/orchestra.pid; do
  if [ -f "$f" ]; then kill "$(cat "$f")" 2>/dev/null; rm -f "$f"; fi
done
if command -v docker >/dev/null; then
  ids=$(docker ps -q --filter label=orchestra.sandbox=1 2>/dev/null); [ -n "$ids" ] && docker kill $ids >/dev/null
fi
echo "Orchestra est arrêté."
