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
python3 scripts/homelabctl.py render <slug>                 # imprime o host.env
python3 scripts/homelabctl.py render <slug> --sync          # imprime o sync.env
sudo python3 scripts/homelabctl.py render <slug> --write --ambos
```

`render --write` grava em `[caminhos] config` (`/etc/homelab-storage-admin`),
com backup `.bak-<data>` quando o conteúdo muda. O `install-agent.sh` chama o
render **só para o que falta**: nunca sobrescreve `host.env` nem `sync.env`
existentes; para aplicar uma mudança de TOML, rode o `render --write`.

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
| `[features]` | `samba`, `discos`, `snapshots`, `restic`, `copia_fria`, `ufw`, `terminal`, `apt`, `qbittorrent`, `jellyfin`, `pihole`, `gitea`, `portal`, `credenciais`, `django_admins` (bool) |
| `[[discos]]` | `device`, `papel` (`dados`, `snapshot`, `backup`, `jellyfin`), `tamanho`, `modelo`, `removivel` |

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

Samba em `/srv/samba`, Caddy próprio em HTTP:80, DNS por nome (`.local`, mDNS),
portal interno, backup local do Credenciais e superuser dos apps Django pelo
agente. Identidade é do Credenciais: `CREDENTIALS_MANAGE_USERS=1` bloqueia
`/usuarios/` no Storage Admin. Overlay `docker-compose.moya.yml`.

### Host novo

1. `python3 scripts/homelabctl.py detect` e revise caminhos, IP e papéis.
2. `python3 scripts/homelabctl.py init --escrever` grava
   `hosts/<slug>/host.toml`.
3. `sudo python3 scripts/homelabctl.py render <slug> --write --ambos`
   (ou rode `sudo ./install-agent.sh`, que gera o que falta).
4. `./deploy.sh` e `sudo scripts/stacks/apps-sync.sh --apply`.

As dependências seguem as features: `homelabctl requisitos <slug>` lista o que
o host precisa (`obrig` derruba o `install-agent.sh`, `opc` só avisa). Host com
`samba = false` não precisa de `smbd`; com `discos = false`, nem de `parted`.
