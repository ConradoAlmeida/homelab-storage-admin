# Teste e deploy das mudanças de Torrents

## Objetivo

Subir no Pi o que já está neste clone: refresh do andamento sem seleção indevida e o botão Organizar séries. O moya não entra.

## Escopo

Clone local em `main` e o checkout do Pi em `/opt/stacks/homelab-storage-admin`. Sem `install-agent.sh`, sem moya, sem clicar em Organizar séries no ar.

## Decisões

- Pytest local antes de qualquer commit. Se falhar, parar.
- Um commit, Conventional Commits, porque os dois comportamentos dividem os mesmos arquivos. Sem `.env`, `data/` ou segredo.
- Push só `git push origin main`, fast-forward. Sem force.
- No Pi, backup dos configs do host como no checklist de `docs/INSTALACAO.md`, depois `./deploy.sh` (ele faz `git pull --ff-only` e o compose). `install-agent.sh` só se o próprio `deploy.sh` imprimir que o agente divergiu. `agent/` não mudou.
- Smoke: agente ativo, login em `http://192.168.0.150:8060/login/` com HTTP 200, `docker compose ps` do web. Não disparar a organização na biblioteca real.
- Se o smoke falhar, rollback no commit anterior, como em `docs/INSTALACAO.md`, e parar.

## Passos

- [x] `uv run pytest` neste clone.
- [ ] Commit e push de `main`.
- [ ] Backup no Pi e `./deploy.sh`.
- [ ] Smoke. Sem VM: a mudança não passa por Samba, restic nem disco.

## Verificação

Pytest verde. Pi com o container web no ar e o login respondendo 200.

## Estado

Plano fechado em 2026-11-04. Pytest: 302 passed, 6 skipped (2026-11-04).
