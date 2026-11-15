# Migração do moya para compose nativo (Caddy e Gitea)

## Objetivo

Tirar `moya-caddy` e `moya-gitea` do controle do Portainer e passá-los a
`compose.yaml` versionáveis no host, como as outras 11 apps do moya e como o
Pi. Efeitos: stack reproduzível, sobrevive a reinstalar o Portainer, o
`apps-sync` volta a enxergar a pasta (prune), e o Caddy do moya pode usar
`apps.caddy` + `import`, aposentando o modo inline.

## Escopo

- Entra: `moya-caddy` (stack `/data/compose/4`, inexistente no host) e
  `moya-gitea` (stack `/data/compose/3`, idem).
- Não entra: Portainer. Ele fica **parado** no fim, com o volume intacto,
  como caminho de rollback. A remoção definitiva é outro passo, depois de
  alguns dias.
- Não muda: nomes `.local`, HTTP:80, Pi-hole, `.local` por nome. O moya não
  conversa com o Pi.

## Decisões

- `caddy`: `/opt/stacks/caddy`, imagem local `caddy:latest` (a mesma que roda
  hoje, sem pull), `container_name: moya-caddy`, `network_mode: host`,
  `./:/etc/caddy:ro`, volumes `moya-caddy_caddy_data` e
  `moya-caddy_caddy_logs` reaproveitados **pelo nome**.
- `gitea`: `/opt/stacks/gitea`, imagem `gitea/gitea:latest`, mesmo nome de
  container, mesmas portas (`222:22`, `3000:3000`), mesmo env
  (`USER_UID=1000`, `USER_GID=1000`, `GITEA_CUSTOM=/data/gitea`) e o volume
  `moya-gitea_gitea_data` reaproveitado pelo nome. Sem cópia de dados.
- Backup antes de qualquer `stop`: `gitea dump` + `docker inspect` dos dois +
  cópia do `Caddyfile` + tar do volume do Caddy.
- Rollback: `docker compose down` na pasta nova e subir de novo pelo
  Portainer (a definição da stack continua no volume dele).

## Passos

- [x] 1. Backups em `/home/conrado/backups/2026-11-15-migracao/`: `gitea dump`
      (3,7 GB, 27 repos, DB SQL), `inspect` dos dois containers, `Caddyfile`,
      tar do `caddy_data` e os dois `rollback-*.sh`.
- [x] 2. `/opt/stacks/caddy`: `compose.yaml` + `Caddyfile` copiado; `stop`/`rm`
      do container do Portainer; `up -d`; 13 rotas em 200/302 e `caddy
      validate` rc=0.
- [x] 3. Perfil `moya` em `apps.caddy` + `import` (`b285b78`); modo inline
      removido do script e dos testes (21 testes de `apps-sync`).
- [x] 4. `/opt/stacks/gitea`: `compose.yaml` com o volume pelo nome;
      `stop`/`rm`; `up -d`; API 1.27.3, 27 repos, clone HTTP e SSH na 222.
- [ ] 5. Portainer parado (container + compose), volume preservado.
      Pendente: decisão do dono, depois de alguns dias rodando assim.
- [x] 6. Docs, plano e deploy; bancada de VM nos dois perfis.

## Verificação

- `docker inspect` do container novo mostra os mesmos volumes e portas.
- 13 nomes `.local` com 200/302; `apps-sync --perfil moya --apply` idempotente.
- Gitea: `/api/v1/version` 200, repositórios de `moya-dev`, `lucas.duarte` e
  `flight-controls` presentes, `git ls-remote` na porta 222.
- Caddyfile e apps.caddy gerados sem bloco manual duplicado.

## Resultado

- Caddy e Gitea rodam de `/opt/stacks/{caddy,gitea}`, com os volumes
  `moya-caddy_caddy_data`, `moya-caddy_caddy_logs` e
  `moya-gitea_gitea_data` reaproveitados pelo nome. Nenhum dado mudou de
  lugar; `compose down` não foi usado com `-v`.
- `apps.env` do moya: `moya-git` aponta para `/opt/stacks/gitea`. O dry-run
  não acusa mais pasta ausente nem container fora do compose.
- Caddyfile final do moya: dois blocos manuais (`moya-pihole`,
  `moya-weather`) e `import apps.caddy`. Idempotente nas rodadas seguintes,
  com `apps.caddy sem mudanca` e DNS sem mudança.
- O Pi (`b285b78`) segue com `apps.caddy sem mudanca` e DNS wildcard
  confirmado: um só caminho de Caddy nos dois hosts.
- O `gitea dump` só funciona em `/tmp` (`/data` é root e o processo roda como
  `git`); os marcadores antigos `# >>> apps-sync` foram removidos à mão do
  Caddyfile do moya, já que o modo inline não existe mais.
- Pendente: parar o Portainer (volume `portainer_data` intacto), apagar
  `moya-admin.local` no Pi-hole do moya e remover sobras (`/home/conrado/caddy`,
  `/data/compose/*`).

## Estado

Concluído em 2026-11-15, menos o passo 5 (Portainer), que espera decisão do
dono. Bancada de VM: `homelab` e `moya` verdes (`475 passed, 8 skipped`, `8 lab
passed` no homelab, smoke 200 nas 7 rotas dos dois perfis).
