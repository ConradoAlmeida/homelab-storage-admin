# Homelab genérico para Ubuntu Server

## Objetivo

O código atende dois hosts que foram nascendo junto com o projeto: `pi`
(Raspberry Pi 5, `192.168.0.150`) e `moya` (Ubuntu, `192.168.0.10`). O que muda
entre eles está espalhado em três lugares — `case "$PERFIL"` no
`apps-sync.sh`, dois `host.env.*.example` e defaults no `settings.py` — e um
terceiro host exigiria editar código. A meta é: **um host novo = um arquivo de
configuração**, com um configurador que detecta discos, mounts e serviços e
pede confirmação, sem tocar em código.

## Escopo

- Entra: schema de configuração por host, detecção assistida, TUI de confirmação,
  render do `host.env` atual (compatibilidade), remoção dos literais `pi`/`moya`
  do código e gating de feature por disponibilidade real.
- Não entra: orquestração multi-host (Pi e moya continuam ilhas), outras
  distros além de Debian/Ubuntu, formatação/montagem automática de disco pelo
  wizard, segredo dentro do arquivo versionado, mudança de nome do projeto.

## Inventário (varredura)

| Categoria | Onde dói hoje | Volume |
|---|---|---|
| Identidade | `conrado` em scripts, testes, docs e templates | 106 ocorrências |
| Caminhos | `/mnt/nas` em compose, script, settings, agente | 125 ocorrências |
| IPs/domínio | `192.168.0.150` (Pi) fixo no `apps-sync.sh` | 39 ocorrências |
| Perfis | `case "$PERFIL"` (paths, Caddy, DNS, TLS, esquema, upstream) | 9 pontos |
| Config atual | `host.env` com 28 (Pi) e 32 (moya) chaves + 43 `env var` no `settings.py` | 2 arquivos-exemplo |
| Discos/hardware | `/dev/sd*`, `lsblk`, SMART, Btrfs/RAID, `arm64` | 23 + 5 |
| Apps por host | `apps.env` com 4 (Pi) e 12 (moya) linhas | 2 arquivos |
| Módulos | `agent` 8,9k linhas; `core` 6,3k; `backups` 1,6k; `history` 590 | flat, sem `modules/` |

O que importa: **nenhuma** das categorias acima tem um ponto único de verdade.
A varredura por arquivo achou ainda seis amarras que não são só "mais um
perfil":

1. **`apps-sync.sh:112-139`** é o único lugar com o `case pi|moya` (scheme,
   `DATA_DIR`, domínio, DNS, Caddy, TLS, upstream, quarentena, portal). Um
   terceiro perfil cai em `erro "--perfil invalido"`.
2. **DNS e Caddy são obrigatórios** (`apps-sync.sh:830-883`, `:711-717`,
   `:785-805`): só existe modo Pi-hole (`docker exec`, `pihole.toml`) e só
   Caddy em container. Host sem um dos dois falha `--apply` e `--doctor` — não
   existe "modo nenhum".
3. **`deploy.sh:92-96`** deduz o perfil pelo nome da pasta (`moya`) e o bloco
   de qBittorrent/UFW/UPnP (`:106-213`) depende do overlay se chamar
   `homelab`. Um host novo herda comportamento do Pi sem pedir.
4. **`core/config_locais.py:49-52`** (`perfil_do_env`) e
   `config/settings.py:64-68` (`APPS_ENV_FILE`) também derivam o perfil do
   nome do diretório, e conhecem só `pi|moya`.
5. **Inconsistência real:** os exemplos põem
   `APPS_ENV_PATH=/etc/homelab-storage-admin/apps.env` (`host.env.example:23`,
   `host.env.moya.example:20`), mas a doc manda
   `deploy/<perfil>/apps.env` (`docs/INSTALACAO.md:103-106`). Com o caminho do
   exemplo, `perfil_do_env` devolve `""` e a página mostra o comando do Pi
   num host que não é Pi.
6. **O agente carrega defaults do moya no código** (`agent:74-85`, `:2687`
   com `/mnt/data`, `:4082-4097` com `/mnt/data/datasheets` e
   `/home/conrado/<app>`), inclusive quando roda no Pi.

Boa notícia: **não há código específico de Raspberry Pi** (sem `vcgencmd`,
sem `/boot/firmware`); o "pi-ness" é caminho, IP e feature, não plataforma.
E o `install-agent.sh:32` exige `samba`/`parted` sempre, mesmo com as features
desligadas — uma instalação só de arquivos não deveria pedir Samba.

## Schema proposto (esboço)

```toml
# hosts/pi/host.toml — versionado, sem segredo
[host]
nome = "pi"
descricao = "Raspberry Pi 5"
ssh = "conrado@homelab.local"
lan_ip = "192.168.0.150"
zona_dns = "conradhub.com"

[app]
bind = "192.168.0.150:8060"
esquema = "https"            # esquema dos links do painel

[caminhos]
dados = "/mnt/nas"
snapshots = "/mnt/nas/.snapshots"
backup = "/mnt/backup"
downloads = "/mnt/nas/apps/homelab-storage-admin/data/downloads"
stacks = "/opt"
quarentena = "/opt/stacks/_removidos"
estado = "/var/lib/homelab-storage-admin"
sockets = "/run/homelab-storage-admin"
config = "/etc/homelab-storage-admin"

[rotas]                      # o que hoje e o case "$PERFIL"
env = "deploy/pi/apps.env"
dns_ip = "192.168.0.150"
dns_modo = "wildcard"        # wildcard | nome | nenhum
dns_conf = "/opt/stacks/pihole/etc-dnsmasq.d/10-conradhub.com-wildcard.conf"
caddy = { dir = "/opt/stacks/caddy", container = "caddy", porta = "", tls = "import cf", proxy = "import proxy" }
upstream = "lan"             # lan | localhost
dirs_permitidos = ["/opt/stacks", "/opt"]
scan_roots = ["/opt"]

[features]
samba = true
snapshots = true
restic = true
copia_fria = true
ufw = true
terminal = true
apt = true
qbittorrent = true
jellyfin = true
pihole = true
gitea = false
portal = false
credenciais = false
django_admins = false

# Confirmado pelo wizard; o app so mostra, nao monta nem formata.
[[discos]]
device = "/dev/sda1"
fs = "ext4"
papel = ["dados"]            # dados | snapshot | backup | jellyfin
```

O que muda no `moya` fica todo no arquivo: `zona_dns = "local"`,
`dns_modo = "nome"`, `caddy = { container = "moya-caddy", porta = ":80", tls = "", proxy = "reverse_proxy" }`,
`upstream = "localhost"`, `portal = true`, `credenciais = true`, `jellyfin/qbittorrent = false`.

Mapeamento direto para o que existe hoje: `[rotas]` cobre as 20 variáveis que
o `apps-sync.sh` lê (`DNS_IP`, `DNS_MODE`, `DNS_CONF`, `CADDY_*`,
`PIHOLE_*`, `UPSTREAM_HOST`, `QUARANTINE`, `SCAN_ROOTS`, `PORTAL_INI`…);
`[caminhos]` + `[app]` + `[features]` cobrem as 28/32 chaves do `host.env` e
os defaults do `settings.py`.

## Decisões

- **Formato, TUI e escopo definidos em 2026-11-15:** TOML por host, TUI
  `textual` rodando no próprio host e generalização de verdade (perfis como
  dados, `pi|moya` fora do código), começando pelas fases invisíveis 0–2.
- **`hosts/<slug>/host.toml` versionado, sem segredo.** Segredos continuam em
  `.env` (container) e `/etc/homelab-storage-admin/secrets.env` (agente); o
  TOML só aponta caminhos.
- **Render, não revolução.** `homelabctl render` gera o `host.env` que o
  `deploy.sh`, o compose e o agente já leem. Fase 1 não muda comportamento
  nenhum: `hosts/pi` e `hosts/moya` têm que renderizar o `host.env` atual.
- **Perfil vira dado.** `--perfil <slug>` passa a validar contra `hosts/*` em
  vez de `pi|moya`; o `case` do `apps-sync.sh` sai e as diferenças (dir do
  Caddy, container, DNS, TLS, esquema, upstream) vêm do render.
- **Detecção só sugere; nada destrutivo no wizard.** `detect` lê `lsblk -J`,
  `findmnt`, `blkid`, `systemctl`, `ip -j`, `docker ps` e sugere papéis por
  disco (`dados`, `snapshot`, `backup`); formatar/montar continua manual e
  explícito (regra 5).
- **Feature com `requires`.** Cada módulo opcional (Samba, snapshots, restic,
  cópia fria, UFW, terminal, apt, qBittorrent, Jellyfin, Pi-hole, Gitea,
  portal, Credenciais) declara binários/units/caminhos que precisa; a
  capability sai de config + detecção, e o que falta some da UI com motivo
  (regra 4).
- **Presets, não forks.** `pi` e `moya` viram `hosts/pi` e `hosts/moya` com
  `features` explícitas; o que é específico do Pi (Cloudflare/TLS, qBittorrent,
  Jellyfin, Pi-hole) fica atrás de flag, não de `if host == pi`.

## Passos

- [x] 0. Congelar comportamento: capturar o `host.env` efetivo dos dois hosts
      (sem segredo) como fixture e fixar a saída do `apps-sync` por perfil —
      a rede de segurança do render.
- [x] 0b. Alinhar `APPS_ENV_PATH` num único caminho (exemplos x doc) e fazer
      `perfil_do_env`/`APPS_ENV_FILE` lerem o perfil do TOML, não do nome da
      pasta.
- [x] 1. Schema `host.toml` + loader (`core/homelab_config.py`) e
      `hosts/pi`/`hosts/moya` reproduzindo os valores de hoje.
- [x] 2. `homelabctl render`: `host.toml` → `host.env` (+ `sync.env` por
      perfil); teste de equivalência com os arquivos atuais.
- [x] 3. `homelabctl detect`: inspeção read-only + fixtures (`lsblk`,
      `findmnt`, `blkid`, `systemctl`, `ip -j`) com testes golden.
- [x] 4. `homelabctl init`: TUI (identidade → discos/papéis → features →
      revisão/diff → escreve), `--dry-run` por padrão.
- [x] 5. Tirar os literais `pi|moya` do `apps-sync.sh` e do
      `install-agent.sh`; perfil inválido = diretório inexistente.
- [ ] 6. Gating por `requires` + testes Pi-safe (host sem Credenciais/Gitea/
      Pi-hole não gera alerta falso) e modo `dns = "nenhum"` / `caddy`
      opcional no reconciliador (`apps-sync.sh:711-883`).
- [x] 6b. `install-agent.sh` checa dependência por feature (Samba/parted só
      quando `samba`/`discos` estão ligados).
- [ ] 7. Docs: `INSTALACAO` como "Ubuntu Server genérico", `docs/PRESETS.md`
      com pi/moya; `host.env.example` vira referência gerada.
- [ ] 8. Bancada: perfil `generico` criado pelo wizard (não é pi nem moya)
      passando smoke + `--doctor` nos dois sentidos.

## Verificação

- `hosts/pi` e `hosts/moya` renderizam `host.env` idêntico ao atual (diff
  vazio) e a bancada dos dois perfis continua verde.
- Host de teste criado só com TOML + wizard roda sem editar Python/shell.
- `--doctor` no host genérico: 0 erros; features ausentes não viram erro.
- Nenhum segredo em `hosts/`; `git grep` por `SECRET`/`TOKEN` no TOML vazio.

## Riscos

- Renomear pacotes (`core/` → `homelab/`) é mecânico mas grande; fica fora
  deste plano até o schema estabilizar.
- A TUI precisa de dependência nova (`textual`) — roda só no setup, não no
  container.
- Detecção de disco erra em storage exótico (LVM fino, iSCSI); por isso ela
  **sugere** e o dev confirma.

## Estado

Plano aprovado em 2026-11-15.

- 0/0b/1/2 (f8a06be + este commit): fixtures do `host.env` efetivo, TOML dos
  dois hosts, `homelabctl list|check|render|requisitos`, `HOST_PROFILE` no
  settings/compose e `sync.env` no `apps-sync.sh`.
- 5/6b: `apps-sync.sh` sem `case $PERFIL` (sync.env + `HOST_PROFILE`, ambiente
  vence) e `install-agent.sh` aceitando qualquer slug e checando dependência
  por feature (`requisitos`).
- 3/4: `core/homelab_detect.py` (lsblk/findmnt/ip/systemctl/docker com runner
  injetável e fixtures) e `core/homelab_wizard.py` (TUI textual com fallback
  por perguntas; valida o TOML antes de gravar, nunca escreve sem `--escrever`).
- Resta 6 (requires/dns_modo no reconciler), 7 (docs), 8 (bancada).
