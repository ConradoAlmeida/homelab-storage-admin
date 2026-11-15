#!/usr/bin/env bash
# Bancada de VM por perfil: preparar, testar e voltar ao estado inicial.
#
# Roda no HOST (desktop com libvirt), nao dentro da VM.
#
#   scripts/vm/bench.sh snapshot listar
#   scripts/vm/bench.sh snapshot criar base-limpo
#   scripts/vm/bench.sh preparar --perfil homelab|moya [--ref main] [--yes]
#   scripts/vm/bench.sh testar   --perfil homelab|moya [--smoke] [--manter] [--yes]
#   scripts/vm/bench.sh limpar   --perfil homelab|moya [--yes]
#
# Invariante: cada execucao comeca e termina no snapshot <perfil>-pronto.
# base-limpo e a origem (setup-ubuntu-2604.sh) e nunca recebe testes.
set -euo pipefail

VM=${VM:-linux2024}
URI=${URI:-qemu:///system}
GUEST_USER=${GUEST_USER:-conrado}
REPO_URL=${REPO_URL:-https://github.com/ConradoAlmeida/homelab-storage-admin.git}
REPO_DIR=${REPO_DIR:-/home/$GUEST_USER/homelab-storage-admin}
REF=${REF:-main}
BASE=${BASE:-base-limpo}

ACAO=${1:-}
SUB=${2:-}
NOME=${3:-}
PERFIL=""
MANTER=0
SMOKE=0
YES=0
RECRIAR=0

for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --manter) MANTER=1 ;;
    --smoke) SMOKE=1 ;;
    --recriar) RECRIAR=1 ;;
  esac
done
# Segunda passada simples para valores (as flags sao curtas e sem ambiguidade).
prev=""
for arg in "$@"; do
  [[ "$prev" == "--perfil" ]] && PERFIL=$arg
  [[ "$prev" == "--ref" ]] && REF=$arg
  prev=$arg
done

uso() {
  cat <<'TXT'
Uso (no HOST, com libvirt):

  scripts/vm/bench.sh snapshot listar
  scripts/vm/bench.sh snapshot criar <nome>
  scripts/vm/bench.sh snapshot apagar <nome>
  scripts/vm/bench.sh preparar --perfil homelab|moya [--ref main] [--recriar] [--yes]
  scripts/vm/bench.sh testar   --perfil homelab|moya [--smoke] [--manter] [--yes]
  scripts/vm/bench.sh limpar   --perfil homelab|moya [--yes]

Invariante: cada execucao comeca e termina no snapshot <perfil>-pronto.
base-limpo e a origem e nunca recebe testes.
TXT
  exit "${1:-0}"
}

erro() {
  echo "ERRO: $*" >&2
  exit 1
}

v() { virsh -c "$URI" "$@"; }

confirma() {
  local msg=$1
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi
  [[ -t 0 ]] || erro "operacao destrutiva ($msg); repita com --yes"
  read -r -p "$msg [s/N] " resposta
  [[ "$resposta" =~ ^[sSyY]$ ]] || erro "cancelado"
}

existe_snapshot() {
  # Captura a lista antes de filtrar: com pipefail, o grep -q fecha o pipe e o
  # virsh termina com SIGPIPE (141), derrubando o pipeline.
  local lista
  lista=$(v snapshot-list "$VM" --name 2>/dev/null || true)
  grep -qx "$1" <<<"$lista"
}

liga_ou_falha() {
  local estado
  estado=$(v domstate "$VM" 2>/dev/null || true)
  [[ -n "$estado" ]] || erro "dominio $VM nao existe em $URI"
  case "$estado" in
    running|paused) ;;
    *) v start "$VM" >/dev/null ;;
  esac
}

desliga() {
  local estado
  estado=$(v domstate "$VM" 2>/dev/null || true)
  [[ "$estado" == "running" ]] || return 0
  v shutdown "$VM" >/dev/null
  for _ in $(seq 1 60); do
    [[ "$(v domstate "$VM")" != "running" ]] && return 0
    sleep 1
  done
  echo "AVISO: shutdown nao concluiu; forcando destroy" >&2
  v destroy "$VM" >/dev/null
  sleep 1
}

ip_guest() {
  v domifaddr "$VM" --source agent 2>/dev/null \
    | awk '$3 == "ipv4" && $4 !~ /^127\./ {print $4}' \
    | cut -d/ -f1 | head -1
}

espera_guest() {
  local ip=""
  for _ in $(seq 1 90); do
    ip=$(ip_guest)
    [[ -n "$ip" ]] && break
    sleep 2
  done
  [[ -n "$ip" ]] || erro "guest agent nao respondeu em $VM (IP nao descoberto)"
  echo "$ip"
}

guest() {
  ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=10 "$GUEST_USER@$IP" "$@"
}

prepara_guest() {
  guest "test -d $REPO_DIR" >/dev/null 2>&1 || guest "git clone --quiet $REPO_URL $REPO_DIR"
  # FETCH_HEAD funciona para branch, tag ou sha e deixa o clone no commit certo.
  guest "cd $REPO_DIR && git fetch --quiet origin $REF && git checkout --force --quiet FETCH_HEAD && git clean -fdq && git log --oneline -1"
}

rodar_smoke() {
  local base="http://$IP:8060"
  local falhou=0 code
  guest "cd $REPO_DIR && ./deploy.sh >/tmp/deploy-vm.log 2>&1" || {
    guest "tail -20 /tmp/deploy-vm.log" || true
    return 1
  }
  # O deploy.sh sobe o container e sai; migracoes ainda rodam por alguns
  # segundos. Esperar a primeira resposta evita 000 por pressa.
  for _ in $(seq 1 45); do
    code=$(guest "curl -s -o /dev/null -w '%{http_code}' $base/login/" 2>/dev/null || true)
    [[ "$code" == "200" || "$code" == "302" ]] && break
    sleep 2
  done
  echo "    login respondeu: ${code:-sem resposta}"
  [[ "$code" == "200" || "$code" == "302" ]] || falhou=1
  for rota in /login/ / /saude/ /backups/ /containers/ /sistema/ \
              /sistema/config/ /sistema/rotas/ /sistema/servicos/; do
    # -L: as rotas internas redirecionam para o login sem sessao; o que importa
    # e nao haver 5xx e o login render.
    code=$(guest "curl -s -L -o /dev/null -w '%{http_code}' $base$rota")
    echo "    $rota -> $code"
    [[ "$code" == "200" ]] || falhou=1
  done
  return "$falhou"
}

case "$ACAO" in
  snapshot)
    case "$SUB" in
      listar)
        v snapshot-list "$VM" --name
        ;;
      criar)
        [[ -n "$NOME" ]] || erro "informe o nome do snapshot"
        if existe_snapshot "$NOME"; then
          erro "snapshot $NOME ja existe (apague com: snapshot apagar $NOME)"
        fi
        confirma "desligar $VM para criar o snapshot $NOME"
        desliga
        v snapshot-create-as "$VM" "$NOME" --description "bancada" >/dev/null
        echo "==> snapshot $NOME criado com $VM desligada"
        ;;
      apagar)
        [[ -n "$NOME" ]] || erro "informe o nome do snapshot"
        existe_snapshot "$NOME" || erro "snapshot $NOME nao existe"
        confirma "apagar o snapshot $NOME"
        v snapshot-delete "$VM" "$NOME" >/dev/null
        echo "==> snapshot $NOME apagado"
        ;;
      *) uso 2 ;;
    esac
    ;;

  preparar)
    [[ "$PERFIL" == "homelab" || "$PERFIL" == "moya" ]] || erro "--perfil homelab|moya"
    existe_snapshot "$BASE" || erro "snapshot $BASE nao existe; rode setup-ubuntu-2604.sh e crie o base-limpo"
    confirma "reverter $VM para $BASE (descarta o estado atual)"
    desliga
    v snapshot-revert "$VM" "$BASE" >/dev/null
    liga_ou_falha
    IP=$(espera_guest)
    echo "==> $VM em $IP; preparando perfil $PERFIL"
    prepara_guest
    guest "cd $REPO_DIR && sudo bash scripts/vm/perfil-$PERFIL.sh"
    desliga
    ALVO="$PERFIL-pronto"
    if existe_snapshot "$ALVO"; then
      if [[ "$RECRIAR" -eq 1 ]]; then
        v snapshot-delete "$VM" "$ALVO" >/dev/null
      else
        erro "snapshot $ALVO ja existe; use --recriar para atualizar"
      fi
    fi
    v snapshot-create-as "$VM" "$ALVO" --description "perfil $PERFIL" >/dev/null
    echo "==> snapshot $ALVO criado"
    ;;

  testar)
    [[ "$PERFIL" == "homelab" || "$PERFIL" == "moya" ]] || erro "--perfil homelab|moya"
    ALVO="$PERFIL-pronto"
    existe_snapshot "$ALVO" || erro "snapshot $ALVO nao existe; rode: preparar --perfil $PERFIL"
    confirma "reverter $VM para $ALVO"
    desliga
    v snapshot-revert "$VM" "$ALVO" >/dev/null
    liga_ou_falha
    IP=$(espera_guest)
    echo "==> $VM em $IP; testando perfil $PERFIL"
    FALHOU=0
    if ! guest "cd $REPO_DIR && uv sync --dev --frozen >/tmp/uv.log 2>&1 && uv run manage.py check"; then
      guest "tail -5 /tmp/uv.log" || true
      FALHOU=1
    fi
    if ! guest "cd $REPO_DIR && uv run pytest -q"; then
      FALHOU=1
    fi
    if [[ "$PERFIL" == "homelab" ]]; then
      if ! guest "cd $REPO_DIR && sudo bash scripts/vm/run-lab-tests.sh"; then
        FALHOU=1
      fi
    else
      if guest "test -d /home/$GUEST_USER/moya_credenciais_app"; then
        if ! guest "cd $REPO_DIR && bash scripts/vm/run-unit-tests.sh"; then
          FALHOU=1
        fi
      else
        echo "    AVISO: moya_credenciais_app ausente; rodei so a suite do Storage" >&2
      fi
    fi
    if [[ "$SMOKE" -eq 1 ]]; then
      if ! rodar_smoke; then
        FALHOU=1
      fi
    fi
    if [[ "$MANTER" -eq 1 ]]; then
      echo "==> VM ligada em http://$IP:8060 (--manter)"
      exit "$FALHOU"
    fi
    desliga
    v snapshot-revert "$VM" "$ALVO" >/dev/null
    echo "==> $VM devolvida ao snapshot $ALVO"
    exit "$FALHOU"
    ;;

  limpar)
    [[ "$PERFIL" == "homelab" || "$PERFIL" == "moya" ]] || erro "--perfil homelab|moya"
    ALVO="$PERFIL-pronto"
    existe_snapshot "$ALVO" || erro "snapshot $ALVO nao existe"
    confirma "reverter $VM para $ALVO (descarta o estado atual)"
    desliga
    v snapshot-revert "$VM" "$ALVO" >/dev/null
    echo "==> $VM no estado inicial ($ALVO)"
    ;;

  ""|-h|--help|ajuda)
    uso 0
    ;;

  *)
    uso 2
    ;;
esac
