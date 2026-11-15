# UI e docs depois dos atalhos gerados

## Objetivo

Fechar as pontas que ficaram com a virada "um arquivo por host": a página
**Configuração** ainda descrevia `services.ini` como arquivo editável e o
`apps.env` como "rotas do Caddy e DNS do Pi". Quem lê a tela hoje é induzido a
editar um artefato.

## O que estava velho (encontrado)

- `core/config_locais.py`: `services.ini` com "Atalhos da home do painel" e
  "vale ao recarregar a página"; `apps.env` só "rotas e DNS".
- `templates/system_config.html`: alerta mandando editar `services.ini`.
- Testes da página usavam `/etc/homelab-storage-admin/apps.env` como caminho do
  env, que não é mais o real.
- Nada mais na UI cita `services.ini`, `portainer` ou o path antigo do env
  (checado em `templates/`, `static/` e `core/`).

## Decisões

- A página continua somente leitura; ela **diz o que é gerado** em vez de
  esconder o arquivo. `ArquivoConfig` ganhou `gerado: bool` e a linha mostra o
  `tag` "gerado" (componente do `ui.css`).
- O `services.ini` aparece nos dois perfis (existe nos dois), com vigência
  "após `apps-sync --apply`"; a linha do `apps.env` só aparece com
  `APPS_ENV_PATH` preenchido, como antes.

## Passos

- [x] 1. `core/config_locais.py`: campo `gerado`, textos de `services.ini` e
      `apps.env`.
- [x] 2. `templates/system_config.html`: tag "gerado" e alerta novo.
- [x] 3. Testes: caminho real do env, flag `gerado`, perfil moya sem a linha do
      env mas com a vigência do `apps-sync`.
- [x] 4. Deploy no moya e conferência da página autenticada (200, com o tag e o path real).
- [x] 5. Bancada de VM nos dois perfis (`8 lab passed`, smoke 200).

## Backlog (não entra agora)

| Item | Por quê |
|---|---|
| `--doctor --fix` | corrigir só o que é gerado (apps.caddy, DNS, atalhos); hoje é reler e `--apply` |
| `--descobrir` sugerir `atalho=`/`grupo=` | a descoberta ainda pensa só em rota |
| Limpar backups datados | `/etc/.../apps.env.bak-20261115`, `host.env.bak-*`, `services.ini.bak-*` |
| CI do repo: `shellcheck` em `scripts/stacks` | o script é o caminho crítico de rede |
| CI do portal (Gitea) | hoje os testes só rodam à mão/em container |
| Ícone `portainer.svg` órfão no portal | sem card que use; remover junto de outra mexida no projeto |

## Verificação

- `pytest` verde (8 testes da página, incluindo o `tag`).
- Página autenticada no moya mostra `services.ini` com "gerado" e a vigência
  do `apps-sync`.

## Estado

Concluído em 2026-11-15 no moya (deploy `e71985b`) e na bancada. Falta o
`./deploy.sh` no Pi, que é do dono.
