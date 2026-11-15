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

- [ ] 1. Limpar as referências no repo e ajustar os dois testes.
- [ ] 2. `uv run pytest` no clone local.
- [ ] 3. Bench na VM (perfil homelab) depois do commit.
- [ ] 4. Pi: remover `cockpit.*.lan` do `Caddyfile`, recarregar o Caddy e
      trocar o `/etc/motd.d/cockpit`.
- [ ] 5. Deploy do Pi e do moya no HEAD (comentário do `services.ini` do Pi
      incluído).

## Verificação

- `grep -ri cockpit` no repo não devolve referência a serviço (só o comentário
  do agente sobre `udisksd`).
- `pytest` 453/8 e bench homelab verdes.
- `dig +short cockpit.conradhub.com @192.168.0.150` vazio; `curl` no vhost
  antigo responde 410 como os outros nomes `.lan` removidos.
- Card do Cockpit ausente no dashboard do Pi.

## Estado

Autorizado em 2026-11-15 ("prioridade é código limpo").
