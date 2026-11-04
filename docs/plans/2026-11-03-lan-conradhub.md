# Zona LAN `homelab.lan` → `conradhub.lan`

## Objetivo

Alinhar a zona DNS da LAN ao domínio público `conradhub.com`:
`storage.conradhub.lan` (LAN) e, mais tarde, `storage.conradhub.com` (Tunnel).
Este plano é **só a zona `.lan`**. Tunnel/Access/HTTPS público ficam para outra
sessão.

## Escopo

**No Pi (live):**

- Pi-hole local DNS (`/opt/stacks/pihole/etc-pihole/hosts/custom.list` e
  `pihole.toml`)
- Caddy (`/opt/stacks/caddy/Caddyfile`)
- Django `.env` do stack: `DJANGO_ALLOWED_HOSTS` e
  `DJANGO_CSRF_TRUSTED_ORIGINS`

**Neste repo:**

- Docs (`REDE`, `SEGURANCA`, `CONTEXTO`, `INSTALACAO`, `ARQUITETURA`,
  `ARMAZENAMENTO`)
- `.env.example`, `services.ini.example`, `templates/torrents.html`
- Testes que cravam `storage.homelab.lan`

**Fora:**

- Hostname Linux `homelab`, Samba, Avahi, wsdd (`HOMELAB.local`)
- Cloudflare Tunnel / `conradhub.com`
- Tailscale admin console (passo manual)
- moyaserver (não usa estes vhosts do Caddy do Pi)
- Renomear o branch `fix/senha-feedback`; o trabalho sai de um branch novo

## Decisões

- Mapeamento 1:1: `X.homelab.lan` → `X.conradhub.lan`.
  `homelab.lan` (a máquina) → `conradhub.lan`.
- **Aliases:** manter os nomes `*.homelab.lan` no Pi-hole e no Caddy durante a
  transição. Canonical nos docs = `*.conradhub.lan`.
- Caddy: o mesmo bloco com os dois hosts
  (`http://storage.homelab.lan, http://storage.conradhub.lan { ... }`).
  Cockpit: bloco extra `https://cockpit.conradhub.lan { tls internal ... }`
  (cert interno novo) **e** o bloco antigo.
- Não mudar `hostname` do SO.
- Branch `chore/lan-conradhub` a partir de `fix/senha-feedback` (o Pi está nesse
  commit; não reverter a correção de senha).
- Deploy no Pi: Caddy + Pi-hole + `.env` Django. Sem `install-agent.sh`.

## Nomes

| Hoje | Canonical novo | IP |
|---|---|---|
| `homelab.lan` / `homelab.local` | `conradhub.lan` (+ alias antigo) | 192.168.0.150 |
| `storage.homelab.lan` | `storage.conradhub.lan` | idem |
| `nas.homelab.lan` | `nas.conradhub.lan` | idem |
| `cockpit.homelab.lan` | `cockpit.conradhub.lan` | idem |
| `dockge.homelab.lan` | `dockge.conradhub.lan` | idem |
| `pihole.homelab.lan` | `pihole.conradhub.lan` | idem |
| `jellyfin.homelab.lan` | `jellyfin.conradhub.lan` | idem |

## Passos

- [x] Branch `chore/lan-conradhub` desde `fix/senha-feedback`.
- [x] Repo: exemplos, templates, docs, testes (canonical `*.conradhub.lan`;
      aliases `*.homelab.lan` citados em REDE/SEGURANCA como transição).
- [x] Pi-hole: acrescentar as linhas `conradhub` em `hosts/custom.list` **e**
      no array de `pihole.toml` (os dois precisam bater). Reload FTL.
- [x] Caddy: dual-host nos blocos HTTP; bloco extra HTTPS cockpit. Backup do
      Caddyfile. `docker exec caddy caddy reload --config /etc/caddy/Caddyfile`
      (ou restart do container se reload falhar).
- [x] Django `.env` no Pi: incluir hosts/origens `*.conradhub.lan` (manter os
      antigos). Recriar o container do app (`./deploy.sh` ou
      `docker compose up -d` **sem** `git pull origin main`, que apagaria o
      branch). O clone do Pi está em `fix/senha-feedback`.
- [x] Pytest local. `dig`/`curl` no Pi para os nomes novos.
- [x] Commit Conventional Commits. Push. Deploy dos ficheiros do repo no Pi
      só se o `.env`/docs precisarem do clone atualizado — Caddy/Pi-hole não
      estão neste git. Clone do Pi não foi atualizado (ALLOWED_HOSTS já vale
      pelo `.env`; o exemplo de curl no template fica no próximo deploy).
- [x] Dizer ao dono: Tailscale console → split DNS, acrescentar
      `conradhub.lan` (hoje só `homelab.lan`).

## Verificação

```bash
uv run pytest tests/test_views.py tests/test_layout_files.py -q
# no Pi, com o resolver do Pi-hole:
dig +short storage.conradhub.lan @127.0.0.1
dig +short storage.homelab.lan @127.0.0.1   # alias ainda responde
curl -sI http://storage.conradhub.lan/login/ | head -5
curl -sI https://cockpit.conradhub.lan/ --insecure | head -5
```

VM `linux2024`: este passo é DNS/Caddy **do Pi**. Pytest local chega. Não
inventar laboratório de Pi-hole na VM.

## Estado

Executado em 2026-11-03. Branch `chore/lan-conradhub` a partir de
`fix/senha-feedback` (`f8ca255`). VM `linux2024` **não** rodou (passo é
DNS/Caddy do Pi).

**Pytest local:** `87 passed, 16 subtests passed` em
`tests/test_views.py tests/test_layout_files.py tests/test_compartilhado.py`.

**Pi (SSH `conrado@192.168.0.150`), backups `*-20261103-222503`:**

- Pi-hole: 7 nomes `*.conradhub.lan` acrescentados em `pihole.toml` e
  `hosts/custom.list`; aliases `*.homelab.lan` mantidos. `pihole reload` não
  existe no v6 (imprimiu o help); FTL já tinha pego o `pihole.toml` via
  inotify. `pihole reloaddns` em seguida.
- Caddy: dual-host HTTP + bloco extra `https://cockpit.conradhub.lan`.
  `docker exec caddy caddy reload --config /etc/caddy/Caddyfile` ok.
- Django `.env`: hosts/origens novos, antigos mantidos,
  `DJANGO_SECURE_COOKIES=0`. Recreate sem git pull:
  `docker compose --env-file /etc/homelab-storage-admin/host.env -f docker-compose.yml -f docker-compose.homelab.yml up -d --no-build --force-recreate web`.
  Clone do Pi permanece em `fix/senha-feedback`.

**dig @127.0.0.1 no Pi:** `storage.conradhub.lan`, `conradhub.lan`,
`nas`/`cockpit`/`dockge`/`pihole`/`jellyfin.conradhub.lan` e os aliases
`storage.homelab.lan` / `homelab.lan` → `192.168.0.150`.

**curl:** `http://storage.conradhub.lan/login/` e o alias → `200`;
`https://cockpit.conradhub.lan/` e o alias → `200` (HTTP/2).

Pendência do dono: Tailscale console → split DNS, Restrict to domain
acrescentar `conradhub.lan`.
