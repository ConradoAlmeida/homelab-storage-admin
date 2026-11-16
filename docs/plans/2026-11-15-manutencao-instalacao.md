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

- `uv run pytest` verde em cada commit.
- `bash -n` + `shellcheck` nos scripts alterados.
- Bancada: `bench.sh testar --perfil generico|homelab|moya --smoke --yes`.
- Produção: `render --write`, `./deploy.sh`, `--doctor` e `doctor` no Pi e no
  moya; `/login/` 200 nos dois.
- `homelabctl bootstrap --sim` num tmp sem tocar em `/etc`.

## Riscos

- `deploy.sh` mais rígido pode parar um deploy de emergência; o rollback é
  `git revert` do commit (os checks são só leitura).
- `doctor` com falso positivo em host sem docker/mount ativo vira ruído; por
  isso esses dois níveis são `aviso`.
- Remover o preset do `apps-sync` quebra host que nunca rodou `render`: a
  mensagem de erro passa a dizer exatamente o comando.

## Estado

Codigo dos 15 itens concluido em 2026-11-15 (um commit por item, `pytest`
verde). Falta a validacao: bancada `generico`/`homelab`/`moya`, deploy no Pi e
no moya, e o registro no `CONTEXTO.md`. Autorizado: lista completa, deploy no
Pi, arm64 so em `main`.
