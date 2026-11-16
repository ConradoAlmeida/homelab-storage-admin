# Hosts e presets

[← Voltar ao README](../README.md) · [Instalação](INSTALACAO.md) · [Contexto](CONTEXTO.md)

> O que muda entre hosts vive em `hosts/<slug>/host.toml`. O `host.env` e o
> `sync.env` são **gerados** dele: são artefatos, não se editam no host.

---

## Fluxo

```bash
python3 scripts/homelabctl.py list                 # hosts versionados
python3 scripts/homelabctl.py check                # valida todos os TOMLs
python3 scripts/homelabctl.py detect               # só lê: propõe um TOML
python3 scripts/homelabctl.py init                 # wizard (TUI ou perguntas)
python3 scripts/homelabctl.py init --escrever      # grava hosts/<slug>/host.toml
python3 scripts/homelabctl.py doctor <slug>        # preflight: o que falta? (só lê)
python3 scripts/homelabctl.py bootstrap <slug>     # env, .env e pacotes (dry-run)
python3 scripts/homelabctl.py render <slug>                 # imprime o host.env
python3 scripts/homelabctl.py render <slug> --sync          # imprime o sync.env
sudo python3 scripts/homelabctl.py render <slug> --write --ambos
```

`render --write` grava em `[caminhos] config` (`/etc/homelab-storage-admin`),
com backup `.bak-<data>` quando o conteúdo muda. O `install-agent.sh` chama o
render **só para o que falta**: nunca sobrescreve `host.env` nem `sync.env`
existentes; para aplicar uma mudança de TOML, rode o `render --write`.

O `pi` e o `moya` já rodam com os dois arquivos renderizados (2026-11-15);
mudar o comportamento deles é editar `hosts/<slug>/host.toml` e rodar o render
no host — não editar `/etc/homelab-storage-admin/*.env`.

O `check` avisa quando o `host.env` ou o `sync.env` instalado difere do TOML
(drift silencioso era o problema: mudar o TOML e esquecer o render). O
`doctor <slug>` é o preflight completo e sai 1 em erro: env fora de sync,
dependência obrigatória ausente, `.env` com modo ≠ 600 ou segredo de exemplo,
mount que não existe, `apps.env` ausente e unit de boot diferente. Aviso
(opcional ausente, docker fora do PATH, unit não instalada) não muda o exit
code. Nada é escrito: cada achado imprime o comando que conserta.

O `detect` só faz leitura (`lsblk`, `findmnt`, `ip`, `systemctl`, `docker`) e o
`init` nunca formata, monta ou apaga disco: os papéis sugeridos só decidem o
que a UI mostra depois.

---

## Schema

Tabela `[seção] chave` — as chaves obrigatórias são validadas pelo loader
(`core/homelab_config.py`):

| Seção | Chaves |
| --- | --- |
| `[host]` | `nome` (slug), `descricao`, `ssh`, `lan_ip`, `repo` |
| `[app]` | `site_name`, `bind_addr`, `bind_port`, `compose_overlay` (vazio = só o `docker-compose.yml`) |
| `[caminhos]` | `dados`, `snapshots`, `backup`, `dados_app`, `stacks`, `quarentena`, `estado`, `sockets`, `config` |
| `[armazenamento]` | `proprietario`, `snapshot_backend`, `snapshot_denylist`, `prefixos_permitidos`, `mounts`, `firewall_safe_ports` |
| `[rotas]` | `esquema`, `apps`, `dominio`, `dns_ip`, `dns_modo`, `dns_conf`, `pihole_dir`, `pihole_container`, `upstream`, `dirs_permitidos`, `scan_roots`, `portal_ini` |
| `[rotas.caddy]` | `dir`, `container`, `porta`, `tls`, `proxy` (dispensável com `upstream = "nenhum"`) |
| `[boot]` | `unit`, `descricao`, `esperar_ip`, `esperar_mounts`, `antes`, `depois` (opcional; host sem ela não gera unit) |
| `[features]` | `samba`, `discos`, `snapshots`, `restic`, `copia_fria`, `ufw`, `terminal`, `apt`, `qbittorrent`, `jellyfin`, `pihole`, `gitea`, `portal`, `credenciais`, `django_admins` (bool) |
| `[[discos]]` | `device`, `papel` (`dados`, `snapshot`, `backup`, `jellyfin`), `tamanho`, `modelo`, `removivel` |

Chave nova com valor óbvio tem default no loader (porta 8060, `snapshots` e
`dados_app` derivados de `dados`, `stacks = /opt`, `dns_modo`/`upstream =
nenhum`, `dns_ip` = `lan_ip`), então um TOML antigo continua válido depois de
um pull. `[host] schema` versiona o arquivo: um TOML mais novo que a ferramenta
é recusado com a instrução de atualizar o repo. O que exige decisão
(`backup`, `proprietario`, `dns_conf` com DNS ativo, `apps`) segue obrigatório.

`dns_modo` é `wildcard` (um `address=/dominio/IP`), `nome` (uma entrada por
app) ou `nenhum` (host sem DNS gerenciado). `upstream` é `lan` (Caddy fala com
o IP da LAN), `localhost` (compose publica em 127.0.0.1) ou `nenhum` (host sem
proxy reverso). O `apps-sync.sh` pula Caddy/DNS sem erro nesses dois últimos.

Segredos **não** entram no TOML: ficam no `.env` do container e no ambiente do
agente.

---

## Presets

### `pi` — Raspberry Pi 5

NAS principal: Btrfs em `/mnt/nas`, TLS pelo Cloudflare, Pi-hole com wildcard
`*.conradhub.com`, qBittorrent/Jellyfin, terminal e UFW pela UI. `host.env` em
`/etc/homelab-storage-admin/host.env`, overlay `docker-compose.homelab.yml`.

### `moya` — moyaserver

Samba em `/mnt/data` (RAID), Caddy próprio em HTTP:80, DNS por nome (`.local`,
mDNS), portal interno, backup local do Credenciais e superuser dos apps Django
pelo agente. Dados de apps em `/mnt/data/apps/<slug>`. Identidade é do
Credenciais: `CREDENTIALS_MANAGE_USERS=1` bloqueia `/usuarios/` no Storage
Admin. Overlay `docker-compose.moya.yml`.

### Host novo (runbook)

Do Ubuntu Server limpo até a app no ar. O `homelabctl` não instala o SO nem
formata disco: o que ele não sabe fazer, ele manda fazer.

1. **Base do sistema** — usuário com sudo no grupo `docker`, Docker + Compose
   (`sudo apt install docker.io docker-compose-v2` ou o repo oficial), e
   Python 3.11+ para o `homelabctl`.
2. **Clone**:
   ```bash
   sudo mkdir -p /opt/stacks && sudo chown "$USER": /opt/stacks
   git clone https://github.com/ConradoAlmeida/homelab-storage-admin.git \
     /opt/stacks/homelab-storage-admin
   cd /opt/stacks/homelab-storage-admin
   ```
3. **Disco de dados** (manual): particione, formate e monte em
   `[caminhos] dados` (ex.: `/mnt/nas`), com entrada persistente no `fstab`.
   Backup em disco separado — o wizard de backup recusa o disco do sistema.
4. **TOML do host**:
   ```bash
   python3 scripts/homelabctl.py detect          # só lê: propõe o TOML
   python3 scripts/homelabctl.py init            # wizard; --escrever grava
   python3 scripts/homelabctl.py check           # valida todos os hosts
   ```
   Revise IP da LAN, caminhos, mounts e features ligadas.
5. **Bootstrap** (dry-run primeiro):
   ```bash
   python3 scripts/homelabctl.py bootstrap <slug>
   sudo python3 scripts/homelabctl.py bootstrap <slug> --escrever --apt
   ```
   Grava `host.env`/`sync.env` em `[caminhos] config`, cria o `.env` a partir
   do `.env.example` com segredo aleatório (`600`) e instala os pacotes das
   features obrigatórias. Nunca sobrescreve arquivo existente: para trocar um
   env já instalado é `render <slug> --write --ambos`. Se o host tiver
   `[boot]`, gere a unit com `homelabctl boot <slug> --write` e instale em
   `/etc/systemd/system/`.
6. **Agente**:
   ```bash
   sudo HOST_ENV_PROFILE=<slug> ./install-agent.sh
   ```
   Sem `hosts/<slug>/host.toml` o script para e pede o `init` — não existe
   mais preset embutido.
7. **Preflight e deploy**:
   ```bash
   python3 scripts/homelabctl.py doctor <slug>   # 0 erros antes de seguir
   ./deploy.sh                                   # falha em erro do doctor
   sudo bash scripts/stacks/apps-sync.sh --apply
   ```
   O `deploy.sh` recusa `.env` com modo diferente de `600` ou
   `DJANGO_SECRET_KEY` de exemplo, e termina rodando o `--doctor` do apps-sync:
   erro de rota/DNS/atalho derruba o deploy (aviso, como o token sem sudo,
   continua aviso).
8. **Smoke**: `/login/` respondendo em `http://<BIND_ADDR>:<BIND_PORT>/login/`,
   `systemctl is-active homelab-storage-agent` e
   `docker compose ... ps` com o container `web` saudável.

As dependências seguem as features: `homelabctl requisitos <slug>` lista o que
o host precisa (`obrig` derruba o `install-agent.sh`, `opc` só avisa). Host com
`samba = false` não precisa de `smbd`; com `discos = false`, nem de `parted`.
