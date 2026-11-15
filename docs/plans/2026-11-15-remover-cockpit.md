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
- [ ] 4. Pi (sudo do dono): tirar `cockpit.*.lan` do `Caddyfile`, recarregar
      o Caddy, remover `/etc/motd.d/cockpit` e instalar o motd novo, e rodar
      `install-agent.sh` (o commit mexeu num comentário do agente).
- [x] 5. Deploy do Pi e do moya no HEAD (`6571c7a`); `services.ini` do Pi
      sem o comentário do cockpit; agente do moya reinstalado.

## Verificação

- `grep -ri cockpit` no repo: zero fora de `docs/plans/`.
- `pytest` 453/8 e bench homelab/moya verdes.
- Card do Cockpit ausente no dashboard do Pi (o bloco `[cockpit]` já tinha
  saído do `services.ini` real).
- Pendente no Pi até o passo 4: `cockpit.*.lan` no `Caddyfile`,
  `/etc/motd.d/cockpit` e o comentário antigo no agente instalado (o
  `deploy.sh` avisa "agente diferente" só por causa disso).

## Estado

Repo e hosts em `6571c7a`. Falta só o bloco que exige `sudo` no Pi.
