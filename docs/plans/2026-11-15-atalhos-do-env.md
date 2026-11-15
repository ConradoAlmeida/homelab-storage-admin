# Um arquivo só: rotas e atalhos no apps.env

## Objetivo

Deixar **um** arquivo editável por host (`deploy/<perfil>/apps.env`). Hoje a
mesma app exige três edições — env (rota), `services.ini` (atalho do painel) e
HTML do portal (card) — e as duas últimas são artefatos, não configuração.
O `--apply` passa a gerar os três: `apps.caddy`, DNS, `services.ini` e a lista
que o portal do moya consome.

## Escopo

- Entra: flags de apresentação no env (`atalho=`, `nome=`, `descricao=`,
  `cor=`, `icone=`), geração de `services.ini` e `apps-portal.ini`, leitura
  dessa lista pelo portal Flask, checks no `--doctor`, testes e docs.
- Não entra: descoberta automática de atalho (nada aparece sem `atalho=`),
  formato novo (continua INI para os dois consumidores), mudança no
  `core/services.py` (o painel segue lendo INI como hoje).
- Não muda: perfis `pi`/`moya`, quarentena, confirmações, allowlist do agente.

## Decisões

- **Um env, dois artefatos gerados.** O script renderiza:
  - `DATA_DIR/services.ini` — atalhos do painel (consumido por
    `core/services.py`, sem alteração de código);
  - `/var/lib/homelab-storage-admin/apps-portal.ini` — mesma INI, só as apps
    com `atalho=portal`; o portal monta o diretório de estado read-only.
- **Padrão é não aparecer.** Sem `atalho=`, a app tem rota e DNS mas nenhum
  card. `atalho=painel`, `atalho=portal` ou `atalho=painel+portal`. A curadoria
  atual (3 no Pi, 2 no moya) vira flag; adicionar ao painel é decisão explícita.
- **Texto único por app.** `nome=` e `descricao=` valem para os dois
  consumidores; `icone=` só o portal usa (o painel mostra a inicial). Preferi
  não duplicar texto agora — se um dia o portal precisar de copy diferente,
  entra `descricao_portal=` sem quebrar nada.
- **Ordem = ordem do env.** `order` é 10, 20, 30… na sequência das linhas, sem
  flag. Reordenar o painel = reordenar o env.
- **Arquivo gerado tem marcador e backup.** Primeira execução num host com
  `services.ini` manual: copia para `services.ini.bak-<data>` e substitui. Dono
  e permissão são preservados (`preserva_dono`). Ausência do `DATA_DIR` (Pi sem
  NAS montado) é aviso, não erro.
- **Portal lê a lista, não o HTML.** `app.py` passa a montar os cards a partir
  da INI (`APPS_PORTAL_INI`), com fallback de ícone para a inicial. Cor vem em
  hex no env e vira `--card-accent` no CSS; os nomes `data-color` saem. O card
  estático "Moya AI — coming soon" continua no template.
- **`--doctor` cobre os novos artefatos**: `services.ini`/`apps-portal.ini`
  diferente do renderizado, arquivo ausente e `atalho`/`cor`/`icone` inválidos
  (esses barram já na validação).

## Passos

- [x] 1. `apps-sync.sh`: parse e validação das flags de apresentação;
      `SCHEME`, `DATA_DIR`, `SERVICES_INI` e `PORTAL_INI` por perfil.
- [x] 2. Render + apply idempotente dos dois arquivos (marcador, backup,
      dono, aviso quando o diretório não existe); resumo no dry-run.
- [x] 3. `--doctor` compara os dois arquivos gerados.
- [x] 4. `deploy/pi/apps.env` e `deploy/moya/apps.env`: migrar os atalhos de
      hoje para flags (Pi: dockge, pihole, jellyfin; moya: versoes,
      credenciais no painel e 10 no portal; `moya-portal` sem atalho;
      portainer já removido).
- [x] 5. Testes em `tests/test_apps_sync.py`: renderização, defaults,
      `atalho=nao`, backup sem marcador, portal só no moya, doctor apontando
      divergência e flags inválidas.
- [x] 6. Portal (`moya_portal_interno`): `app.py` lê a INI, template itera,
      CSS por variável, compose monta o estado read-only, testes do projeto.
- [ ] 7. Aplicar nos dois hosts, conferir painel e portal, `--doctor` limpo.
- [ ] 8. Bancada de VM nos dois perfis; docs (`REDE`, `SISTEMA`, `ROTINAS`,
      `INSTALACAO`, `CONTEXTO`) e este plano.

## Verificação

- `apps.env` é o único arquivo editado para adicionar app com atalho; painel e
  portal refletem a mudança sem tocar em `services.ini`/HTML.
- `--apply` duas vezes seguidas: segundo run diz "atalhos sem mudanca" e não
  reescreve nada.
- `services.ini` antigo: primeira execução gera `.bak-<data>` e o novo arquivo
  com o mesmo dono.
- `--doctor` acusa `services.ini` editado à mão e volta ao normal no `--apply`.
- `pytest` verde (inclui os testes do portal) e bancada `linux2024` nos dois
  perfis.

## Estado

Em andamento (2026-11-15): código, testes, envs e docs prontos; falta aplicar
nos hosts e rodar a bancada.
