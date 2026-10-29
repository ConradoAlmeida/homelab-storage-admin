#!/usr/bin/env bash
# Smoke somente leitura para o moyaserver (ou uma VM com o mesmo layout).
# Nao autentica, nao altera nada e nao chama operacoes destrutivas.
#
#   bash scripts/vm/smoke-moyaserver.sh
#
# Variaveis opcionais:
#   CREDENCIAIS_URL=http://127.0.0.1:8080
#   STORAGE_URL=http://127.0.0.1:8060
set -u

CREDENCIAIS_URL="${CREDENCIAIS_URL:-http://127.0.0.1:8080}"
STORAGE_URL="${STORAGE_URL:-http://127.0.0.1:8060}"
falhas=0

checar() {
    local nome="$1" esperado="$2" url="$3"
    local codigo
    codigo="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || echo 000)"
    if [[ "$codigo" == "$esperado" ]]; then
        echo "OK   ${nome} (${codigo})"
    else
        echo "FALHA ${nome}: esperado ${esperado}, obtido ${codigo}"
        falhas=$((falhas + 1))
    fi
}

echo "== HTTP =="
checar "Credenciais /health/" "200" "${CREDENCIAIS_URL}/health/"
checar "Credenciais /login/" "200" "${CREDENCIAIS_URL}/login/"
checar "Storage /" "302" "${STORAGE_URL}/"

echo "== Containers =="
for nome in moya-credenciais homelab-storage-admin; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$nome"; then
        echo "OK   container ${nome}"
    else
        echo "FALHA container ${nome} nao esta rodando"
        falhas=$((falhas + 1))
    fi
done

echo "== Agentes =="
if command -v systemctl >/dev/null 2>&1; then
    for unidade in moya-credenciais-agent homelab-storage-agent; do
        if systemctl is-active --quiet "$unidade"; then
            echo "OK   ${unidade}"
        else
            echo "FALHA ${unidade} inativo"
            falhas=$((falhas + 1))
        fi
    done
else
    echo "AVISO systemctl indisponivel; pulei os agentes"
fi

echo
if [[ "$falhas" -eq 0 ]]; then
    echo "SMOKE_OK"
    exit 0
fi
echo "SMOKE_FALHAS=${falhas}"
exit 1
