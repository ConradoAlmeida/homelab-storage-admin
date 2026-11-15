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

- [ ] 1. Backups em `/home/conrado/backups/2026-11-15-migracao/`: `gitea dump`,
      `inspect` dos dois containers, `Caddyfile`, tar do volume do Caddy.
- [ ] 2. `/opt/stacks/caddy`: `compose.yaml` + `Caddyfile` copiado; `stop`/`rm`
      do container do Portainer; `up -d`; 13 rotas conferidas.
- [ ] 3. Perfil `moya` passa a `CADDY_MODO=arquivo` (`apps.caddy` + `import`);
      modo inline removido do script e dos testes.
- [ ] 4. `/opt/stacks/gitea`: `compose.yaml` com o volume pelo nome;
      `stop`/`rm`; `up -d`; login, repositórios e `git ls-remote` na 222.
- [ ] 5. Portainer parado (container + compose), volume preservado.
- [ ] 6. Docs, plano e deploy; bancada de VM nos dois perfis.

## Verificação

- `docker inspect` do container novo mostra os mesmos volumes e portas.
- 13 nomes `.local` com 200/302; `apps-sync --perfil moya --apply` idempotente.
- Gitea: `/api/v1/version` 200, repositórios de `moya-dev`, `lucas.duarte` e
  `flight-controls` presentes, `git ls-remote` na porta 222.
- Caddyfile e apps.caddy gerados sem bloco manual duplicado.

## Estado

Em andamento (2026-11-15).
