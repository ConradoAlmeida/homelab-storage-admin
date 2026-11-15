# Fechar pendências da sessão da bancada

## Objetivo

Versionar os planos que ficaram só no disco, destravar o clone local e levar
`main` (`c3984e3`) aos dois hosts reais.

## Escopo

- Commit dos planos `2026-11-14-verificacao-deploy-vm.md` e
  `2026-11-15-bancada-vm-perfis.md`.
- Clone local (`~/development/homelab-storage-admin`, 75 commits atrás): pull.
- Deploy no Pi (`homelab.local`, `c469d39`, 72 commits atrás) e no moya
  (`10.72.60.181`, `0da95c5`, 11 commits atrás).
- Fora: arm64, E2E de identidade, resize do disco da VM (destrói snapshots;
  fica para a conversa seguinte), rascunho do Cockpit.

## Decisões

1. Deploy é **só código**: `git diff` de `*/migrations/*.py` vazio para os dois
   intervalos, então não há mudança de schema.
2. O clone local tem um rascunho do Cockpit (docs + 2 planos não versionados)
   que uma sessão posterior deixou **de fora de propósito**
   (`2026-11-10-disco-share-dump.md`). Vai para patch + `git stash`, sem
   reaplicar; nada do rascunho entra em `main`.
3. Rollback do deploy: como o `deploy.sh` só puxa `main`, voltar exige
   `git reset --hard <sha>` e `docker compose up -d --build` no host.

## Passos

- [ ] 1. Copiar os dois planos para o worktree e commitar.
- [ ] 2. Salvar patch + untracked do clone local, `git stash -u`, `git pull`.
- [ ] 3. Pi: `./deploy.sh` e verificação (container, rotas, agente).
- [ ] 4. moya: `./deploy.sh` e verificação (container, rotas, Credenciais).
- [ ] 5. Remover o worktree temporário e fechar.

## Verificação

- `main` e ambos os hosts em `c3984e3`.
- Rotas 200 no Pi (via Caddy) e no moya (`127.0.0.1:8060`).
- Agente `active` nos dois; sem aviso de agente divergente no deploy.
- Clone local em `main` com `git stash list` contendo o rascunho do Cockpit.

## Estado

Autorizado em 2026-11-15.
