# Página "Rotas e atalhos"

## Objetivo

A página **Configuração** mostra caminhos de arquivos, não o que está declarado.
Quem administra precisa abrir o `apps.env` por SSH para saber quais apps existem,
onde aparecem e se a última execução do `apps-sync` aplicou aquilo. Uma página
somente leitura no painel resolve isso sem tirar o env como fonte da verdade.

## Escopo

- Entra: leitura do `deploy/<perfil>/apps.env` e do estado aplicado
  (`/var/lib/homelab-storage-admin/apps.aplicados`), tela `/sistema/rotas/`,
  item no menu Sistema, link a partir de Configuração, testes e docs.
- Não entra: editar o env pela UI, `--apply` pela UI, checar DNS/Caddy/portas
  (isso é o `--doctor`, que precisa do host), teste de conexão em cada app.
- Não muda: formato do env, geração de atalhos, allowlist do agente.

## Decisões

- **Ler os dois arquivos, nunca o host.** O painel já é somente leitura; a
  página só lê o env do checkout e o estado que o `apps-sync` grava. Nada de
  nova operação no agente (a allowlist continua fechada).
- **Montagens no Compose base**: `./deploy:/app/deploy:ro` (o env do perfil,
  sempre igual ao checkout, sem depender de rebuild) e
  `/var/lib/homelab-storage-admin:/var/lib/homelab-storage-admin:ro` (estado e
  lista do portal, 0644). Os dois existem nos dois hosts.
- **"Aplicado" é comparação, não palpite**: a linha do estado tem
  `key|fqdn|upstream|dir|flags`; a app é `aplicado` quando a tupla bate e
  `pendente` quando o env mudou depois do último `--apply`. App no estado que
  saiu do env aparece como `fora do env`.
- **Sem arquivo, sem 500**: env ausente, estado ausente ou linha inválida viram
  aviso na tela (regra 4 do repositório).
- **Texto e default iguais ao script**: `nome` derivado do fqdn do mesmo jeito
  que o `apps-sync` (base antes do primeiro ponto, `-` vira espaço, primeira
  letra maiúscula), para a tela não mentir sobre o que o painel/portal mostram.
- **Grupo só vale para o portal**: a coluna mostra o grupo com tag "portal";
  app sem `atalho=portal` mostra `—`. Sem isso o `grupo=services` default
  sugere que a app está numa seção onde ela não aparece.

## Passos

- [x] 1. `core/apps_env.py`: parse do env (5 campos + flags), default de nome,
      leitura do estado e comparação (`aplicado`/`pendente`/`fora do env`).
- [x] 2. `config/settings.py`: `APPS_ENV_FILE` (caminho no container derivado do
      perfil de `APPS_ENV_PATH`) e `APPS_STATE_FILE`.
- [x] 3. `docker-compose.yml`: as duas montagens read-only.
- [x] 4. `SystemRotasView` + `core/urls.py` + item no menu (+ link em
      Configuração).
- [x] 5. `templates/system_rotas.html`: `page-head`, resumo em `card`, tabela
      com `table-toolbar` (busca + filtro de atalho) e `data-table`, `tag` para
      atalho e estado.
- [x] 6. Testes: parser (flags, default, inválido, ausente), comparação de
      estado e página (200, tags, perfil Pi sem portal, arquivos ausentes).
- [x] 7. Docs (`SISTEMA`, `ROTINAS`, `CONTEXTO`, `ARQUITETURA` se citar a tela) e
      este plano.
- [x] 8. Deploy no moya e conferência autenticada; bancada nos dois perfis.

## Verificação

- `/sistema/rotas/` no moya lista as 12 apps, 2 com atalho de painel e 11 de
  portal, todas `aplicado`; editar o env sem `--apply` faz a linha virar
  `pendente` (teste automatizado cobre a comparação).
- No Pi a página mostra 4 apps, 3 com atalho de painel e nenhum de portal.
- Sem `deploy/` ou sem estado a página abre com aviso, sem 500.
- `pytest` verde e bancada `linux2024` nos dois perfis.

## Resultado

- Página em `/sistema/rotas/`, item novo no menu Sistema e link em
  Configuração. Nada é escrito e o agente não é chamado.
- No moya (deploy `dd56252`): 12 rotas, 2 no painel, 11 no portal, 1 sem
  atalho, nenhuma pendente; `http://…local` porque o overlay seta
  `APPS_SCHEME: http`.
- Teste com o `apps.aplicados` real e o env do moya: todas `aplicado`, sem
  linha inválida e sem app fora do env.
- `511 passed` local (16 testes novos: parser, flags, default de nome,
  estados, envs reais e a página com/sem arquivos).
- Bancada `linux2024` verde nos dois perfis (`8 lab passed`, smoke 200).

## Estado

Concluído em 2026-11-15; falta o `./deploy.sh` no Pi, que é do dono.
