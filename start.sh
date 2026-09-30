#!/usr/bin/env bash
# Équivalent Linux/macOS de start.ps1 (utilisé aussi pour les tests).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data logs
if [ -f data/orchestra.pid ] && kill -0 "$(cat data/orchestra.pid)" 2>/dev/null; then
  echo "Orchestra tourne déjà (PID $(cat data/orchestra.pid))"; exit 0
fi
PY=${PYTHON:-python3}
if [ ! -f .env ]; then cp .env.example .env; fi
if ! grep -qE '^ORCHESTRA_TOKEN=\S+' .env; then
  TOKEN=$($PY -c 'import secrets;print(secrets.token_hex(32))')
  sed -i.bak "s/^ORCHESTRA_TOKEN=.*/ORCHESTRA_TOKEN=$TOKEN/" .env && rm -f .env.bak
fi
export PYTHONPATH="$PWD/platform${PYTHONPATH:+:$PYTHONPATH}"
$PY -m orchestra init
if command -v npm >/dev/null && [ ! -f platform/dashboard/dist/index.html ] && [ -f platform/dashboard/package.json ]; then
  (cd platform/dashboard && npm ci --no-audit --no-fund && npm run build)
fi
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  [ -n "$(docker images -q orchestra-runtime:latest)" ] || docker compose --profile build-only build
fi
nohup $PY -m orchestra serve > logs/api.out.txt 2> logs/api.err.txt &
echo $! > data/orchestra.pid
for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8765/api/health >/dev/null; then break; fi; sleep 0.5
done
curl -sf http://127.0.0.1:8765/api/health >/dev/null || { echo "L'API ne répond pas (logs/api.err.txt)"; exit 1; }
echo "Orchestra est lancé : http://127.0.0.1:8765"
