# Instalação e manutenção: fechar as pontas do host genérico

## Objetivo

Reduzir passo manual na instalação de um Ubuntu novo e eliminar o drift
silencioso na manutenção (TOML mudou e o host ficou velho; deploy mentindo
verde; literal de host voltando para o shell).

## Escopo

Os 15 itens levantados na revisão de 2026-11-15, em quatro lotes:

1. **P0 — resquícios e drift**
   - `deploy.sh`: remover o `case ... moya` (código morto, comentário falso).
   - Drift TOML ↔ `/etc`: `check` avisa e `doctor` falha quando o `host.env`
     ou o `sync.env` instalado difere do render.
   - `deploy.sh`: `qbittorrent` pela feature, não por `COMPOSE_OVERLAY=*homelab*`.
2. **Ferramenta**
   - `homelabctl doctor <slug>`: TOML, env em sync, requisitos, `.env`,
     mounts, docker, `apps.env` e unit de boot.
   - `homelabctl bootstrap`: detect → TOML → render → `.env` → requisitos
     (`--apt` opcional), sem nunca sobrescrever.
   - Unit de boot gerada do TOML (`[boot]`), com equivalência testada.
3. **Deploy mais rígido**
   - Falha em **erro** do `--doctor` (aviso continua aviso).
   - Recusa `.env` com modo ≠ 600 ou `SECRET_KEY` de exemplo.
4. **Guardrails e docs**
   - CI: `bash -n` + `shellcheck` nos scripts de produção; build arm64 só
     em push para `main`.
   - Teste proibindo literal `pi|moya` em `deploy.sh`, `install-agent.sh` e
     `scripts/stacks/apps-sync.sh`.
   - Teste de equivalência `host.env.example`/`host.env.moya.example` × render.
   - Retenção de `.bak` no render (3 mais recentes).
   - `schema` + defaults no loader: chave nova não quebra TOML antigo.
   - Runbook de instalação no `PRESETS.md` (clone, pacotes, disco, `.env`).

## Decisões

- `apps-sync.sh` perde o fallback de presets: perfil vem de `--perfil`,
  `HOST_PROFILE` (ambiente) ou `host.env`; sem nenhum, falha dizendo como
  renderizar. Os dois hosts de produção já têm `sync.env`.
- Defaults do TOML só onde o valor é óbvio (porta 8060, `stacks = /opt`,
  caminhos derivados de `dados`); `backup`, `proprietario` e `dns_conf` com
  DNS ativo continuam obrigatórios.
- `bootstrap` só escreve com `--escrever` (mesma regra do `init`) e só roda
  `apt-get` com `--apt` **e** root.
- `.env` gerado usa segredo aleatório e `ALLOWED_HOSTS` do `lan_ip`; nunca
  sobrescreve `.env` existente.
- Unit de boot: `[boot]` opcional com `unit`, `descricao`, `esperar_ip`,
  `esperar_mounts`, `antes` e `depois`. O Pi mantém o arquivo byte a byte.
- Doctor: `erro` para o que impede o deploy (env ausente/diferente, dep
  obrigatória, `.env` fraco, `apps.env` ausente); `aviso` para o resto
  (opcionais, docker ausente, mount que é só diretório).

## Passos

- [x] 1. `deploy.sh` sem o literal `moya`.
- [x] 2. Drift TOML ↔ `/etc` no `check`; erro no `doctor`.
- [x] 3. `homelabctl doctor`.
- [x] 4. `deploy.sh` falha em erro do `--doctor`.
- [x] 5. `deploy.sh` valida `.env` (600 e segredo não-exemplo).
- [x] 6. `homelabctl bootstrap`.
- [x] 7. CI com `bash -n` + `shellcheck`.
- [x] 8. Teste anti-literal `pi|moya` nos scripts de produção.
- [x] 9. Teste de equivalência exemplos × render.
- [x] 10. Retenção de `.bak`.
- [x] 11. `schema` + defaults no loader.
- [x] 12. Runbook de instalação nos docs.
- [x] 13. `qbittorrent` por feature no `deploy.sh`.
- [x] 14. Unit de boot gerada do TOML.
- [x] 15. CI arm64 em push para `main`.

## Verificação

- [x] `uv run pytest` verde em cada commit (final: `619 passed, 8 skipped`).
- [x] `bash -n` + `shellcheck --severity=warning` nos quatro scripts de root
  (`deploy.sh`, `entrypoint.sh`, `install-agent.sh`, `apps-sync.sh`): 0 achados.
- [x] Bancada `linux2024`: `generico`, `homelab` (8 testes de laboratório) e
  `moya` (suite unitária do Credenciais) com `--smoke`; `/login/` e as nove
  rotas em 200 nos três, `--doctor` 0 erros.
- [x] Produção em `ab9ea87`: Pi e moya com `render --write --ambos`,
  `./deploy.sh` e `install-agent.sh`; `/login/` 200. `doctor pi` 0/0 e
  `doctor moya` 0 erros/1 aviso (`/srv/samba` não é ponto de montagem).
- [x] `bootstrap` dry-run nos dois hosts (`--config-dir`/`--env-file` em
  `/tmp`): relata e não escreve nada.

## Achados fora do escopo (viram próxima sessão)

- Moyaserver: os shares do Samba vivem em `/srv/samba` no LV do sistema
  (100 GB, 68% usado) e não no RAID `/mnt/data`. O doctor avisa; mover exige
  janela com o Samba parado.
- Pi: `/var/backups/moya-credenciais` foi criado no passado pelo
  `install-agent.sh` e ficou órfão (o script não cria mais); pode ser apagado.

## Estado

Concluido em 2026-11-15. Os 15 itens estao em producao no Pi e no moya
(`ab9ea87`), com bancada verde nos tres perfis. Falhas achadas no caminho e
corrigidas no mesmo lote: o `check` comparava todos os hosts com o `/etc` de
um so, o `DF_MOUNTS` do Pi apontava para o diretorio pai do disco de backup e
o `.env` das VMs usava o segredo de exemplo (recusado pelo deploy novo).
