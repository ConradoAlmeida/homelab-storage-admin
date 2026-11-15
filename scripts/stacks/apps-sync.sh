#!/usr/bin/env bash
# Reconciler do Caddy e do DNS do Pi a partir do apps.env.
#
# O apps.env e a fonte da verdade: cada linha declara uma app exposta pelo
# Caddy. O script compara o declarado com o que esta aplicado (estado em
# /var/lib/homelab-storage-admin/apps.aplicados), gera as rotas, garante o
# wildcard de DNS e aponta o drift de containers e pastas.
#
#   scripts/stacks/apps-sync.sh                  # dry-run: mostra o plano
#   sudo scripts/stacks/apps-sync.sh --apply     # gera Caddy + DNS
#   sudo scripts/stacks/apps-sync.sh --apply --prune-containers
#   sudo scripts/stacks/apps-sync.sh --apply --prune-containers --prune-data
#
# `--prune-containers` roda `docker compose down` (sem -v) so para quem saiu do
# env. `--prune-data` move a pasta para /opt/stacks/_removidos/<key>-<data>,
# nunca apaga. Sem estado anterior nada e removido, so avisado.
set -euo pipefail

APPS_ENV=${APPS_ENV:-/etc/homelab-storage-admin/apps.env}
APPS_STATE=${APPS_STATE:-/var/lib/homelab-storage-admin/apps.aplicados}
STACKS_ROOT=${STACKS_ROOT:-/opt}
CADDY_CONTAINER=${CADDY_CONTAINER:-caddy}
PIHOLE_CONTAINER=${PIHOLE_CONTAINER:-pihole}
DOMAIN=${DOMAIN:-conradhub.com}
DNS_IP=${DNS_IP:-192.168.0.150}
DNS_QUERY_HOST=${DNS_QUERY_HOST:-127.0.0.1}

CADDY_DIR=${CADDY_DIR:-$STACKS_ROOT/stacks/caddy}
CADDYFILE=${CADDYFILE:-$CADDY_DIR/Caddyfile}
CADDY_APPS=${CADDY_APPS:-$CADDY_DIR/apps.caddy}
CADDY_TOKEN_FILE=${CADDY_TOKEN_FILE:-$CADDY_DIR/cloudflare.token}
DNS_CONF=${DNS_CONF:-$STACKS_ROOT/stacks/pihole/etc-dnsmasq.d/10-$DOMAIN-wildcard.conf}
QUARANTINE=${QUARANTINE:-$STACKS_ROOT/stacks/_removidos}
TEST_MODE=${TEST_MODE:-0}

# Pastas que o reconciler nunca move: derrubar o proxy ou o DNS no meio da
# operacao deixaria a casa sem rede.
PROTEGIDOS=("$STACKS_ROOT/stacks/caddy" "$STACKS_ROOT/stacks/pihole")

APLICAR=0
PODAR_CONTAINERS=0
PODAR_DADOS=0
YES=0

declare -A FQDN=() UPSTREAM=() DIR=() FLAGS=()
declare -A ANT_FQDN=() ANT_UPSTREAM=() ANT_DIR=() ANT_FLAGS=()
KEYS=()
ANT_KEYS=()

uso() {
  cat <<'TXT'
Uso: scripts/stacks/apps-sync.sh [--apply] [--prune-containers] [--prune-data] [--yes]

Sem --apply e dry-run: mostra o plano e nao escreve nada.
  --apply             gera /opt/stacks/caddy/apps.caddy, recarrega o Caddy e
                      garante o wildcard *.conradhub.com no Pi-hole
  --prune-containers  `docker compose down` (sem -v) nas apps que sairam do env
  --prune-data        move a pasta das apps removidas para a quarentena
  --yes               nao pergunta antes de cada operacao destrutiva

Os prunes exigem --apply e comparam com o estado da execucao anterior
(/var/lib/homelab-storage-admin/apps.aplicados). Sem esse arquivo, nada e
removido: o script so avisa o que saiu do env.

Formato do apps.env:
  key|fqdn|upstream|dir|flags
TXT
}

erro() {
  echo "ERRO: $*" >&2
  exit 2
}

# `read -a` come o campo vazio no fim da linha; o env usa `...|` para "sem
# flags", entao o delimitador final precisa ser reposto antes do split.
split_linha() {
  local linha=$1 delims=${1//[^|]/}
  IFS='|' read -r -a CAMPOS <<<"$linha"
  while [[ ${#CAMPOS[@]} -lt $(( ${#delims} + 1 )) ]]; do
    CAMPOS+=("")
  done
}

aviso() {
  echo "AVISO: $*" >&2
}

secao() {
  echo
  echo "==> $*"
}

item() {
  echo "    $*"
}

add_key() {
  local k=$1
  local existente
  for existente in "${KEYS[@]:-}"; do
    [[ "$existente" == "$k" ]] && erro "key repetida no $APPS_ENV: $k"
  done
  KEYS+=("$k")
}

valida() {
  local linhas=0
  local erros=0
  local linha key fqdn upstream dir flags campo nome
  local -a campos

  [[ -r "$APPS_ENV" ]] || erro "nao consigo ler $APPS_ENV"
  [[ -d "$STACKS_ROOT" ]] || erro "STACKS_ROOT nao existe: $STACKS_ROOT"

  while IFS= read -r linha || [[ -n "$linha" ]]; do
    linhas=$((linhas + 1))
    linha=${linha%$'\r'}
    [[ -z "${linha// /}" ]] && continue
    [[ "$linha" =~ ^[[:space:]]*# ]] && continue

    split_linha "$linha"
    campos=("${CAMPOS[@]}")
    if [[ ${#campos[@]} -ne 5 ]]; then
      aviso "$APPS_ENV:$linhas: esperava 5 campos (key|fqdn|upstream|dir|flags), achei ${#campos[@]}"
      erros=$((erros + 1))
      continue
    fi
    key=${campos[0]} fqdn=${campos[1]} upstream=${campos[2]} dir=${campos[3]} flags=${campos[4]}
    key=${key// /} fqdn=${fqdn// /} upstream=${upstream// /} dir=${dir// /}
    flags=${flags// /}

    if [[ ! "$key" =~ ^[a-z0-9][a-z0-9-]*$ || ${#key} -gt 40 ]]; then
      aviso "$APPS_ENV:$linhas: key invalida '$key' (use [a-z0-9-], ate 40)"
      erros=$((erros + 1))
    fi
    if [[ ! "$fqdn" =~ ^[a-z0-9][a-z0-9.-]*\.$DOMAIN$ ]]; then
      aviso "$APPS_ENV:$linhas: fqdn '$fqdn' fora de .$DOMAIN"
      erros=$((erros + 1))
    fi
    if [[ ! "$upstream" =~ ^[A-Za-z0-9._-]+:[0-9]{1,5}$ ]]; then
      aviso "$APPS_ENV:$linhas: upstream '$upstream' invalido (host:porta)"
      erros=$((erros + 1))
    fi
    if [[ ! "$dir" =~ ^$STACKS_ROOT(/stacks)?/[a-z0-9][a-z0-9-]*$ ]]; then
      aviso "$APPS_ENV:$linhas: dir '$dir' fora de $STACKS_ROOT/<nome> ou $STACKS_ROOT/stacks/<nome>"
      erros=$((erros + 1))
    fi
    if [[ -n "$flags" ]]; then
      IFS=',' read -r -a campos <<<"$flags"
      for campo in "${campos[@]}"; do
        [[ "$campo" == "manual" ]] || {
          aviso "$APPS_ENV:$linhas: flag desconhecida '$campo' (so 'manual')"
          erros=$((erros + 1))
        }
      done
    fi
    for nome in "${KEYS[@]:-}"; do
      [[ "$nome" == "$key" ]] && { aviso "$APPS_ENV:$linhas: key repetida '$key'"; erros=$((erros + 1)); }
    done
    for nome in "${KEYS[@]:-}"; do
      [[ -n "$nome" && "${FQDN[$nome]:-}" == "$fqdn" ]] && { aviso "$APPS_ENV:$linhas: fqdn repetido '$fqdn'"; erros=$((erros + 1)); }
    done
    for nome in "${KEYS[@]:-}"; do
      [[ -n "$nome" && "${DIR[$nome]:-}" == "$dir" ]] && { aviso "$APPS_ENV:$linhas: dir repetido '$dir'"; erros=$((erros + 1)); }
    done

    KEYS+=("$key")
    FQDN[$key]=$fqdn UPSTREAM[$key]=$upstream DIR[$key]=$dir FLAGS[$key]=$flags
  done <"$APPS_ENV"

  [[ $erros -eq 0 ]] || erro "$erros linha(s) invalida(s) em $APPS_ENV; nada foi alterado"
  [[ ${#KEYS[@]} -gt 0 ]] || erro "$APPS_ENV nao declara nenhuma app"
}

le_estado() {
  local linha key fqdn upstream dir flags
  local -a campos
  [[ -r "$APPS_STATE" ]] || return 0
  while IFS= read -r linha || [[ -n "$linha" ]]; do
    linha=${linha%$'\r'}
    [[ -z "${linha// /}" ]] && continue
    [[ "$linha" =~ ^[[:space:]]*# ]] && continue
    split_linha "$linha"
    campos=("${CAMPOS[@]}")
    [[ ${#campos[@]} -eq 5 ]] || continue
    key=${campos[0]} fqdn=${campos[1]} upstream=${campos[2]} dir=${campos[3]} flags=${campos[4]}
    ANT_KEYS+=("$key")
    ANT_FQDN[$key]=$fqdn ANT_UPSTREAM[$key]=$upstream ANT_DIR[$key]=$dir ANT_FLAGS[$key]=$flags
  done <"$APPS_STATE"
}

declarada() {
  local k
  for k in "${KEYS[@]}"; do
    [[ "$k" == "$1" ]] && return 0
  done
  return 1
}

declarado_fqdn() {
  local k
  for k in "${KEYS[@]}"; do
    [[ "${FQDN[$k]}" == "$1" ]] && return 0
  done
  return 1
}

e_manual() {
  [[ ",${FLAGS[$1]:-}," == *",manual,"* ]]
}

projeto() {
  basename "$1"
}

tem_docker() {
  command -v docker >/dev/null 2>&1
}

containers_do_projeto() {
  docker ps -a --filter "label=com.docker.compose.project=$1" --format '{{.Names}}' 2>/dev/null || true
}

# --- Caddy ----------------------------------------------------------------

gera_apps() {
  local k
  cat <<TXT
# Gerado por scripts/stacks/apps-sync.sh. A fonte da verdade e $APPS_ENV.
# Nao edite este arquivo: ele e reescrito na proxima execucao.
TXT
  for k in "${KEYS[@]}"; do
    e_manual "$k" && continue
    cat <<TXT

${FQDN[$k]} {
	import cf
	import proxy ${UPSTREAM[$k]}
}
TXT
  done
}

conflito_no_caddyfile() {
  local fqdn=$1 linha n conteudo corpo
  local -a linhas=()
  mapfile -t linhas < <(grep -nF "$fqdn" "$CADDYFILE" 2>/dev/null | cut -d: -f1 || true)
  for n in "${linhas[@]:-}"; do
    [[ -n "$n" ]] || continue
    conteudo=$(sed -n "${n}p" "$CADDYFILE")
    conteudo=${conteudo%$'\r'}
    if [[ "$conteudo" != "$fqdn {" && "$conteudo" != "$fqdn{" ]]; then
      item "conflito: $CADDYFILE:$n ja cita $fqdn de forma que o gerador nao sabe remover:"
      item "  $conteudo"
      return 0
    fi
    # O bloco so pode ser removido se o corpo nao tiver chaves aninhadas.
    corpo=$(sed -n "$((n + 1)),/^}$/p" "$CADDYFILE")
    if grep -q '{' <<<"$corpo"; then
      item "conflito: o bloco de $fqdn em $CADDYFILE:$n tem chaves aninhadas"
      item "  remova a mao (ou marque a app como manual) e rode de novo"
      return 0
    fi
  done
  return 1
}

garante_import() {
  # Le o Caddyfile do stdin e devolve com o import no fim: os snippets (cf,
  # proxy) ja estao definidos acima, entao a ordem e segura.
  cat
  printf '\nimport apps.caddy\n'
}

# Remove um bloco de host simples (cabecalho `fqdn {`, corpo sem chaves
# aninhadas, fecha em `}` na coluna 0). Recusa qualquer estrutura diferente.
remove_bloco() {
  local arquivo=$1 fqdn=$2 escapado
  escapado=$(printf '%s' "$fqdn" | sed 's/\./\\./g')
  awk -v alvo="^$escapado[ \t]*\\{[ \t]*$" '
    pula == 1 {
      if ($0 ~ /^[ \t]*\{/) { erro = 1 }
      if ($0 ~ /^\}[ \t]*$/) { pula = 0; next }
      next
    }
    $0 ~ alvo { pula = 1; next }
    { print }
    END { if (erro) exit 3 }
  ' "$arquivo"
}

aplica_caddy() {
  local k tmp backup mudou=0 fqdn
  local -a geradas=()
  local conflitos=0

  [[ -f "$CADDYFILE" ]] || erro "Caddyfile nao encontrado em $CADDYFILE"

  mkdir -p "$CADDY_DIR"

  for k in "${KEYS[@]}"; do
    e_manual "$k" && continue
    fqdn=${FQDN[$k]}
    geradas+=("$fqdn")
    conflito_no_caddyfile "$fqdn" && conflitos=$((conflitos + 1))
  done
  [[ $conflitos -eq 0 ]] || erro "resolva os conflitos acima no Caddyfile e rode de novo; nada foi alterado"

  tmp=$(mktemp "$CADDY_DIR/.apps.caddy.XXXXXX")
  gera_apps >"$tmp"
  if [[ -f "$CADDY_APPS" ]] && cmp -s "$tmp" "$CADDY_APPS"; then
    rm -f "$tmp"
    item "apps.caddy sem mudanca"
  else
    chmod 0644 "$tmp"
    mv -f "$tmp" "$CADDY_APPS"
    item "apps.caddy atualizado: $CADDY_APPS"
    mudou=1
  fi

  # O Caddyfile importa apps.caddy de dentro do container. Se o bind mount
  # nao existe, o import falha e o Caddy antigo continua no ar: melhor parar
  # aqui, antes de editar o Caddyfile.
  if ! docker exec "$CADDY_CONTAINER" test -f /etc/caddy/apps.caddy 2>/dev/null; then
    erro "o container $CADDY_CONTAINER nao ve /etc/caddy/apps.caddy.
    Monte a pasta do Caddy em $CADDY_DIR/compose.yaml, no lugar dos mounts
    de Caddyfile e cloudflare.token:
      - ./:/etc/caddy:ro
    Depois: docker compose up -d && sudo $0 --apply"
  fi

  # Um backup so, antes de qualquer edicao no Caddyfile desta execucao.
  backup="$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"

  if ! grep -qxF 'import apps.caddy' "$CADDYFILE"; then
    cp -p "$CADDYFILE" "$backup"
    tmp=$(mktemp "$CADDY_DIR/.Caddyfile.XXXXXX")
    garante_import <"$CADDYFILE" >"$tmp"
    chmod 0644 "$tmp"
    mv -f "$tmp" "$CADDYFILE"
    item "import apps.caddy adicionado ao Caddyfile (backup: $(basename "$backup"))"
    mudou=1
  fi

  for fqdn in "${geradas[@]:-}"; do
    [[ -n "$fqdn" ]] || continue
    grep -qxF "$fqdn {" "$CADDYFILE" || continue
    tmp=$(mktemp "$CADDY_DIR/.Caddyfile.XXXXXX")
    if ! remove_bloco "$CADDYFILE" "$fqdn" >"$tmp"; then
      rm -f "$tmp"
      erro "o bloco de $fqdn no Caddyfile tem chaves aninhadas; remova a mao e rode de novo"
    fi
    [[ -f "$backup" ]] || cp -p "$CADDYFILE" "$backup"
    chmod 0644 "$tmp"
    mv -f "$tmp" "$CADDYFILE"
    item "bloco de $fqdn saiu do Caddyfile (agora vem de apps.caddy)"
    mudou=1
  done

  caddy_validate || erro "caddy validate falhou; Caddyfile e apps.caddy mantidos, sem reload"
  if [[ $mudou -eq 1 ]]; then
    caddy_reload || erro "caddy reload falhou"
    item "Caddy recarregado"
  else
    item "Caddy ja estava com a configuracao do env"
  fi

  for k in "${KEYS[@]}"; do
    e_manual "$k" || continue
    if ! grep -qF "${FQDN[$k]}" "$CADDYFILE"; then
      aviso "${FQDN[$k]} esta marcada como manual mas nao aparece no Caddyfile"
    fi
  done
}

caddy_validate() {
  local token=""
  if [[ -r "$CADDY_TOKEN_FILE" ]]; then
    token=$(tr -d '\r\n' <"$CADDY_TOKEN_FILE")
  fi
  if [[ -n "$token" ]]; then
    docker exec -e "CLOUDFLARE_API_TOKEN=$token" "$CADDY_CONTAINER" \
      caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
  else
    aviso "sem $CADDY_TOKEN_FILE; validando sem o token da Cloudflare"
    docker exec "$CADDY_CONTAINER" \
      caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
  fi
}

caddy_reload() {
  docker exec "$CADDY_CONTAINER" \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
}

# --- DNS ------------------------------------------------------------------

aplica_dns() {
  local tmp atual=0
  mkdir -p "$(dirname "$DNS_CONF")"
  tmp=$(mktemp "$(dirname "$DNS_CONF")/.wildcard.XXXXXX")
  cat >"$tmp" <<TXT
# Gerado por scripts/stacks/apps-sync.sh. Qualquer nome em *.$DOMAIN
# responde com o Pi; nao ha entrada por app. Entradas exatas no Pi-hole
# (custom.list) continuam valendo e tem precedencia.
address=/$DOMAIN/$DNS_IP
TXT
  if [[ -f "$DNS_CONF" ]] && cmp -s "$tmp" "$DNS_CONF"; then
    rm -f "$tmp"
    item "wildcard DNS sem mudanca: $DNS_CONF"
  else
    chmod 0644 "$tmp"
    mv -f "$tmp" "$DNS_CONF"
    item "wildcard DNS gravado: $DNS_CONF"
    atual=1
  fi

  if [[ "$(docker exec "$PIHOLE_CONTAINER" pihole-FTL --config misc.etc_dnsmasq_d 2>/dev/null | tail -1)" != "true" ]]; then
    docker exec "$PIHOLE_CONTAINER" pihole-FTL --config misc.etc_dnsmasq_d true >/dev/null 2>&1 ||
      erro "nao consegui ligar misc.etc_dnsmasq_d no Pi-hole"
    item "misc.etc_dnsmasq_d ligado no pihole.toml"
    atual=1
  fi

  if [[ $atual -eq 1 ]]; then
    docker restart "$PIHOLE_CONTAINER" >/dev/null 2>&1 || erro "falhou o restart do $PIHOLE_CONTAINER"
    item "Pi-hole reiniciado para ler $DNS_CONF"
  fi

  local tentativa valor
  for tentativa in $(seq 1 20); do
    valor=$(dig +short +time=2 +tries=1 "sync-$tentativa.$DOMAIN" @"$DNS_QUERY_HOST" 2>/dev/null | head -1 || true)
    if [[ "$valor" == "$DNS_IP" ]]; then
      item "wildcard confirmado: *.$DOMAIN -> $DNS_IP"
      return 0
    fi
    sleep 1
  done
  erro "o Pi-hole nao respondeu *.$DOMAIN com $DNS_IP; confira $DNS_CONF e misc.etc_dnsmasq_d"
}

# --- Containers e pastas --------------------------------------------------

lista_removidas() {
  local k
  for k in "${ANT_KEYS[@]}"; do
    declarada "$k" || echo "$k"
  done
}

relata_containers() {
  local k projeto_nome presentes ausentes=0
  if ! tem_docker; then
    aviso "docker nao encontrado; check de containers pulado"
    return 0
  fi
  for k in "${KEYS[@]}"; do
    projeto_nome=$(projeto "${DIR[$k]}")
    presentes=$(containers_do_projeto "$projeto_nome" | paste -sd, -)
    if [[ -z "$presentes" ]]; then
      item "container ausente: $k (projeto compose '$projeto_nome', dir ${DIR[$k]})"
      ausentes=$((ausentes + 1))
    else
      item "container ok: $k -> $presentes"
    fi
  done
  [[ "$ausentes" -eq 0 ]] || item "containers ausentes nao sao iniciados por este script; suba com ./deploy.sh ou docker compose"
}

relata_orfaos() {
  local arquivo pasta declarado k
  local -A vistos=()
  while IFS= read -r arquivo; do
    pasta=$(dirname "$arquivo")
    [[ -n "${vistos[$pasta]:-}" ]] && continue
    vistos[$pasta]=1
    [[ "$pasta" == "$CADDY_DIR" ]] && continue
    [[ "$pasta" == "$QUARANTINE" || "$pasta" == "$QUARANTINE"/* ]] && continue
    declarado=0
    for k in "${KEYS[@]}"; do
      [[ "${DIR[$k]}" == "$pasta" ]] && declarado=1
    done
    [[ $declarado -eq 1 ]] && continue
    item "stack fora do env (nao sera tocada): $pasta"
  done < <(find "$STACKS_ROOT" -maxdepth 3 \( -name 'compose.yaml' -o -name 'compose.yml' -o -name 'docker-compose.yml' -o -name 'docker-compose.yaml' \) 2>/dev/null | sort)
}

poda_containers() {
  local k projeto_nome presente
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    projeto_nome=$(projeto "${ANT_DIR[$k]}")
    presente=$(containers_do_projeto "$projeto_nome" | paste -sd, -)
    if [[ -z "$presente" ]]; then
      item "containers de $k ja estao parados"
      continue
    fi
    if [[ ! -d "${ANT_DIR[$k]}" ]]; then
      aviso "$k saiu do env mas ${ANT_DIR[$k]} nao existe; pare os containers a mao"
      continue
    fi
    item "parando containers de $k (projeto '$projeto_nome'): $presente"
    ( cd "${ANT_DIR[$k]}" && docker compose -p "$projeto_nome" down ) ||
      erro "docker compose down falhou para $k"
  done < <(lista_removidas)
}

protegida() {
  local caminho=$1 p
  for p in "${PROTEGIDOS[@]}"; do
    [[ "$caminho" == "$p" ]] && return 0
  done
  return 1
}

poda_dados() {
  local k dir destino
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    dir=${ANT_DIR[$k]}
    [[ -n "$dir" && -d "$dir" ]] || continue
    if protegida "$dir"; then
      aviso "$dir e caminho de infraestrutura; mover para quarentena exige acao manual"
      continue
    fi
    destino="$QUARANTINE/$k-$(date +%Y-%m-%d_%H%M%S)"
    confirma "mover $dir para $destino"
    mkdir -p "$QUARANTINE"
    chmod 0755 "$QUARANTINE"
    mv "$dir" "$destino" || erro "falhou mover $dir para $destino"
    item "quarentena: $dir -> $destino"
    item "revise e apague quando quiser; o script nao apaga pasta de app"
  done < <(lista_removidas)
}

confirma() {
  local msg=$1 resposta
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi
  [[ -t 0 ]] || erro "operacao destrutiva ($msg); repita com --yes"
  read -r -p "    $msg [s/N] " resposta
  [[ "$resposta" =~ ^[sSyY]$ ]] || erro "cancelado"
}

grava_estado() {
  local k dir tmp
  mkdir -p "$(dirname "$APPS_STATE")"
  tmp=$(mktemp "$(dirname "$APPS_STATE")/.apps.XXXXXX")
  {
    echo "# Gerado por scripts/stacks/apps-sync.sh em $(date '+%Y-%m-%d %H:%M:%S')."
    echo "# key|fqdn|upstream|dir|flags aplicados na ultima execucao."
    for k in "${KEYS[@]}"; do
      echo "$k|${FQDN[$k]}|${UPSTREAM[$k]}|${DIR[$k]}|${FLAGS[$k]}"
    done
    # App que saiu do env continua no estado enquanto tiver container ou pasta:
    # e o que permite podar depois sem perder o rastro.
    while IFS= read -r k; do
      [[ -n "$k" ]] || continue
      dir=${ANT_DIR[$k]}
      if [[ -n "$dir" && -d "$dir" ]] ||
         { tem_docker && [[ -n "$(containers_do_projeto "$(projeto "$dir")")" ]]; }; then
        echo "$k|${ANT_FQDN[$k]}|${ANT_UPSTREAM[$k]}|$dir|${ANT_FLAGS[$k]}"
      fi
    done < <(lista_removidas)
  } >"$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$APPS_STATE"
  item "estado gravado: $APPS_STATE"
}

# Entradas exatas no Pi-hole (dns.hosts/custom.list) vencem o wildcard: se o
# nome saiu do env, a resolucao continua ate alguem remover pela UI.
relata_dns_exatos() {
  local nome sobrando=0
  local escapado=${DOMAIN//./\\.}
  if ! tem_docker || ! docker exec "$PIHOLE_CONTAINER" true >/dev/null 2>&1; then
    return 0
  fi
  while IFS= read -r nome; do
    [[ -n "$nome" ]] || continue
    declarado_fqdn "$nome" && continue
    item "Pi-hole ainda tem entrada exata para $nome (fora do env); o wildcard cobre, mas a entrada fica"
    sobrando=1
  done < <(
    docker exec "$PIHOLE_CONTAINER" grep -hoE "\"[^\"]*\.$escapado\"" \
      /etc/pihole/pihole.toml 2>/dev/null | tr -d '"' | awk '{print $NF}' | sort -u
  )
  [[ $sobrando -eq 0 ]] || item "remova essas entradas na UI do Pi-hole (Local DNS) se quiser o DNS so pelo env"
}

# --- Plano ----------------------------------------------------------------

mostra_plano() {
  local k removidas=0 geradas=0 manuais=0
  secao "plano (dry-run; use --apply para escrever)"
  for k in "${KEYS[@]}"; do
    if e_manual "$k"; then
      manuais=$((manuais + 1))
      item "manual: ${FQDN[$k]} (bloco escrito a mao no Caddyfile; upstream ${UPSTREAM[$k]})"
    else
      geradas=$((geradas + 1))
      item "rota: ${FQDN[$k]} -> ${UPSTREAM[$k]}"
    fi
    [[ -d "${DIR[$k]}" ]] || item "pasta ausente: ${DIR[$k]} (a rota ainda pode ser gerada)"
  done
  item "apps: ${#KEYS[@]} declaradas, $geradas geradas, $manuais manuais"

  if [[ ${#ANT_KEYS[@]} -eq 0 ]]; then
    item "sem estado anterior em $APPS_STATE: nenhuma remocao sera feita nesta execucao"
  else
    while IFS= read -r k; do
      [[ -n "$k" ]] || continue
      removidas=$((removidas + 1))
      item "fora do env: $k (${ANT_FQDN[$k]}, ${ANT_DIR[$k]})"
    done < <(lista_removidas)
    [[ $removidas -eq 0 ]] || item "$removidas app(s) sairam do env: --prune-containers e --prune-data tratam delas"
  fi
  relata_containers
  relata_orfaos
  relata_dns_exatos
}

# --- Entrada --------------------------------------------------------------

for arg in "$@"; do
  case "$arg" in
    --apply) APLICAR=1 ;;
    --prune-containers) PODAR_CONTAINERS=1 ;;
    --prune-data) PODAR_DADOS=1 ;;
    --yes) YES=1 ;;
    -h|--help) uso; exit 0 ;;
    *) erro "argumento desconhecido: $arg (veja --help)" ;;
  esac
done

if [[ $PODAR_CONTAINERS -eq 1 || $PODAR_DADOS -eq 1 ]]; then
  [[ $APLICAR -eq 1 ]] || erro "--prune-containers/--prune-data exigem --apply"
fi
if [[ $PODAR_DADOS -eq 1 && $PODAR_CONTAINERS -eq 0 ]]; then
  erro "--prune-data exige --prune-containers: pare a app antes de mover a pasta"
fi

if [[ $APLICAR -eq 1 ]]; then
  if [[ $EUID -ne 0 && "$TEST_MODE" != "1" ]]; then
    erro "--apply precisa de root (sudo): escreve em $STACKS_ROOT e em $APPS_STATE"
  fi
  tem_docker || erro "--apply precisa do docker no PATH"
  command -v dig >/dev/null 2>&1 || erro "--apply precisa do dig para confirmar o DNS"
fi

valida
le_estado

if [[ $APLICAR -eq 0 ]]; then
  mostra_plano
  exit 0
fi

secao "caddy"
aplica_caddy

secao "dns"
aplica_dns

if [[ $PODAR_CONTAINERS -eq 1 ]]; then
  secao "containers fora do env"
  poda_containers
fi

if [[ $PODAR_DADOS -eq 1 ]]; then
  secao "pastas fora do env (quarentena)"
  poda_dados
fi

secao "estado"
grava_estado

secao "dns do Pi-hole"
relata_dns_exatos

secao "resumo"
item "${#KEYS[@]} apps declaradas e aplicadas"
item "Caddy: $CADDY_APPS"
item "DNS: $DNS_CONF"
