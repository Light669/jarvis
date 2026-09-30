#!/usr/bin/env bash
# MVP Orchestra (Linux/macOS) : Python 3.11+ uniquement. Ctrl+C pour tout arrêter.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
mkdir -p data logs
[ -d .venv ] || $PY -m venv .venv
VPY=.venv/bin/python
[ -f data/.deps-installed ] || { $VPY -m pip install -q -e platform && touch data/.deps-installed; }
[ -f .env ] || cp .env.example .env
grep -qE '^ORCHESTRA_TOKEN=\S+' .env || sed -i.bak "s/^ORCHESTRA_TOKEN=.*/ORCHESTRA_TOKEN=$($VPY -c 'import secrets;print(secrets.token_hex(32))')/" .env
rm -f .env.bak
TOKEN=$(grep -E '^ORCHESTRA_TOKEN=' .env | cut -d= -f2-)
$VPY -m orchestra init >/dev/null
[ "$($VPY -c "from orchestra.platform import Platform; p=Platform('.'); print(len(p.agents.list())); p.close()")" = "0" ] && $VPY -m orchestra demo
PORT=$($VPY -c "from orchestra.config import load_config; print(load_config('.').server.port)")
echo "Orchestra : http://127.0.0.1:$PORT/#token=$TOKEN"
( sleep 3; command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:$PORT/#token=$TOKEN" >/dev/null 2>&1 || true ) &
exec $VPY -m orchestra serve
