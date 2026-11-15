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

- [x] 1. Copiar os dois planos para o worktree e commitar (`425f35f`).
- [x] 2. Salvar patch + untracked do clone local, `git stash -u`, `git pull`
      (clone em `425f35f`, limpo; rascunho do Cockpit em `stash@{0}`).
- [x] 3. Pi: `./deploy.sh` — container no ar, `/login/` 200 via Caddy.
      **Pendente:** `sudo ./install-agent.sh` (o agente instalado é de 13/11 e
      não tem as ops `django_admin*`; `sudo` no Pi pede senha).
- [x] 4. moya: `./deploy.sh` — todas as rotas 200, `/usuarios/` 404
      (seção bloqueada por `CREDENTIALS_MANAGE_USERS=1`), agente sem aviso.
- [x] 5. Remover o worktree temporário e fechar.

## Verificação

- `main` e ambos os hosts em `main` (Pi e moya em `425f35f` no momento do deploy).
- Rotas 200 no Pi (via Caddy) e no moya (`127.0.0.1:8060`).
- Pi com agente **divergente** (só unidades iguais) até rodar o
  `install-agent.sh`; moya sem aviso.
- Clone local em `main` com `git stash list` contendo o rascunho do Cockpit.

## Estado

2026-11-15: deploys feitos, sem migrações e sem downtime além do recreate.
O dono rodou `sudo ./install-agent.sh` no Pi: os quatro binários e as units
ficaram idênticos ao repo, o aviso do `deploy.sh` desapareceu e o binário
instalado passou a ter as ops `django_admin*` (32 ocorrências). Worktree
removido; clone local em `main`, limpo, com o rascunho do Cockpit em
`stash@{0}`.

O `host.env` dos dois hosts não tem algumas chaves dos exemplos
(`SYSTEM_MANAGE`, `FIREWALL_MANAGE`, `TERMINAL_ENABLE`, `SSH_LOGIN`…), mas os
defaults do `settings.py` já são `1`: nenhum comportamento mudou.

## Continuação (mesmo dia)

- **CI obrigatório em PR:** `main` passou a exigir o check `test` (GitHub
  Actions, `strict: false`). Push direto continua passando, mas o GitHub
  registra "bypassed rule violations" no push — é o admin usando o bypass.
- **Disco da VM:** 9,8 GB → 18 GB de filesystem (`pvresize` + `lvextend` +
  `resize2fs`). Os três snapshots foram apagados antes, porque o snapshot
  interno guarda o tamanho do disco, e recriados depois (`base-limpo`,
  `homelab-pronto`, `moya-pronto`) com 11 GB livres.
- **Bug encontrado na limpeza:** o `perfil-moya.sh` registrava no manifesto
  `/srv/samba` e `/mnt/data`, que vêm do `setup-ubuntu-2604.sh`, e o
  `clean.sh` apagava os dois (o `base-limpo` perdia o share `e2e`). Corrigido
  em `20d5753`: só entra no manifesto o que o perfil criou.
- **Cockpit:** não está instalado nem rodando em nenhum host (sem pacote, sem
  `cockpit.socket`, porta 9090 fechada). No Pi sobra só `cockpit.*.lan` na
  lista de nomes que respondem 410. O rascunho dos docs continua em `stash@{0}`.
