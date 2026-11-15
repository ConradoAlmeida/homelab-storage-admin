# Remover o Cockpit do código e dos hosts

## Objetivo

Cockpit não é mais usado. Tirar as últimas referências do repositório e o
vhost órfão do Caddy no Pi, para que docs e config descrevam só o que existe.

## Escopo

- Repo: `services.ini.example`, `core/services.py` (docstring),
  `static/css/app.css`, `README.md`, `docs/REDE.md`, `docs/ARQUITETURA.md`,
  `docs/INSTALACAO.md`, `deploy/pi/cloudflared-config.yml.example` e os dois
  testes que citam o serviço.
- Pi: `Caddyfile` (lista de nomes que respondem 410) e `/etc/motd.d/cockpit`.
- Fora: os `.bak` do Pi-hole (backup, ficam), o comentário do agente sobre
  `udisksd`/apt (fato técnico, mantém) e o `services.ini` do Pi (o card já
  saiu; sobra um comentário).

## Decisões

1. Nada de código novo: é remoção. `icon = cockpit` deixa de existir na lista
   de ícones conhecidos e cai no genérico se alguém escrever isso no
   `services.ini` real.
2. O `deploy/pi/motd` é genérico; muda só o destino da instalação, de
   `/etc/motd.d/cockpit` para `/etc/motd.d/homelab-storage`.
3. Os passos que precisam de `sudo` no Pi (`Caddyfile`, `motd.d`) o dono roda;
   o resto já está feito ou não precisa.

## Passos

- [x] 1. Limpar as referências no repo e ajustar os dois testes
      (`6571c7a`, zero ocorrências fora de `docs/plans/`).
- [x] 2. `uv run pytest` no clone local: 453 passed, 8 skipped.
- [x] 3. Bench na VM com o commit novo, snapshots recriados:
      homelab 453+8 lab e moya 138+453, 7 rotas 200 nos dois.
- [x] 4. Pi (2026-11-15): `cockpit.*.lan` saiu do `Caddyfile` (backup
      `Caddyfile.bak-20261115-135858`) e o Caddy recarregou;
      `/etc/motd.d/cockpit` virou `/etc/motd.d/homelab-storage`; o
      `install-agent.sh` rodou e os 4 binários estão em sync.
- [x] 5. Deploy do Pi e do moya no HEAD (`6571c7a`); `services.ini` do Pi
      sem o comentário do cockpit; agente do moya reinstalado.

## Verificação

- `grep -ri cockpit` no repo: zero fora de `docs/plans/`.
- `pytest` 453/8 e bench homelab/moya verdes.
- Card do Cockpit ausente no dashboard do Pi (o bloco `[cockpit]` já tinha
  saído do `services.ini` real).
- No Pi, `curl http://cockpit.homelab.lan/` dá 308 (sem vhost o Caddy manda
  para HTTPS) e `https://cockpit.conradhub.com` não completa o TLS; o nome
  continua sem entrada no Pi-hole.
- `./deploy.sh` no Pi já sai sem o aviso "agente diferente".

## Estado

Concluído em 2026-11-15: repo, Pi e moya sem referência ao Cockpit.
