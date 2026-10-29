#!/usr/bin/env bash
# Roda as suites de unidade/integracao dos dois apps na VM.
#   CREDENCIAIS_DIR=/home/conrado/moya_credenciais_app \
#     bash scripts/vm/run-unit-tests.sh
set -euo pipefail

CREDENCIAIS_DIR="${CREDENCIAIS_DIR:-/home/conrado/moya_credenciais_app}"
STORAGE_DIR="${STORAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

echo "== Credenciais: suite completa =="
cd "$CREDENCIAIS_DIR"
uv sync --frozen
uv run python manage.py test --verbosity 0

echo
echo "== Storage Admin: suite completa com Python 3.12 =="
cd "$STORAGE_DIR"
uv python install 3.12
uv sync --dev --python 3.12 --frozen
uv run --python 3.12 pytest -q

echo
echo "UNIT_TESTES_OK"
