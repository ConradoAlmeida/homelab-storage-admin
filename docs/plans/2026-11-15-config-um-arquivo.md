# Configuração: um editável, dois raros, o resto gerado

## Objetivo

Desde que o `apps.env` passou a gerar rotas, DNS e atalhos, a página
Configuração ficou mentindo por omissão: listava `services.ini` (artefato) ao
lado de `host.env` e `.env` (editáveis), todos com o mesmo peso. A tela deve
dizer o que se edita, o que raramente muda e o que nunca se edita.

## Escopo

- Entra: reorganização da página em três blocos (rotas/atalhos, perfil e
  segredos, gerados), `ArquivoGerado`, testes e docs.
- Não entra: fundir `host.env` no `apps.env` (ciclos diferentes: `deploy.sh` e
  `install-agent.sh` leem o perfil antes do container existir; `.env` é segredo
  que não pode ir para o Git) e edição pela UI.

## Decisões

- **Ordem por frequência, não por arquivo.** O `apps.env` é o primeiro cartão,
  com link para Rotas e atalhos; `host.env`/`.env` viram tabela "perfil e
  segredos"; `services.ini` sai do bloco editável e entra em "gerados" com a
  origem (`atalho=painel`).
- **Nada de tag "gerado" numa tabela de editáveis.** A separação em seção diz
  isso melhor que uma etiqueta no meio das outras linhas.
- **Sem `APPS_ENV_PATH`, aviso no lugar do cartão** (host sem env declarado),
  mantendo o resto da página — nada de 500 nem de bloco vazio.

## Passos

- [x] 1. `core/config_locais.py`: `ArquivoGerado`, `arquivos_config` devolvendo
      `apps_env`/`arquivos`/`gerados`, sem o campo `gerado`.
- [x] 2. `templates/system_config.html`: três seções + SSH + nota de vigência.
- [x] 3. Testes: Pi com e sem env, `gerados` separado, moya com Credenciais,
      página sem `APPS_ENV_PATH`.
- [x] 4. Docs (`SISTEMA`) e este plano.
- [x] 4b. "Como aplicar" em passos numerados (git pull → `--apply` →
      `--doctor`), com `--perfil moya` só no moya; componente `steps-list` no
      `frontend/src.css` e `kit.css` recompilado.
- [x] 5. Deploy nos dois hosts e conferência autenticada; bancada.

## Verificação

- No moya: primeiro bloco com `deploy/moya/apps.env`, tabela com `host.env`,
  `.env` e `.env (Credenciais)`, bloco "gerados" com o `services.ini`.
- No Pi (quando deployar): mesmo layout, sem a linha do Credenciais.
- `pytest` verde e bancada com `/sistema/config/` e `/sistema/rotas/` em 200.

## Resultado

- Configuração com quatro blocos: **Rotas, DNS e atalhos** (`apps.env`, com os
  passos de aplicação), **Perfil e segredos** (`host.env`, `.env`, e o `.env` do
  Credenciais no moya), **Gerados** (`services.ini` e a lista do portal) e
  **SSH**.
- Passos de aplicação, com o comando real por perfil: `git pull` → `--apply` →
  `--doctor`; `--perfil moya` aparece só no moya (o script assume `pi`).
- A mesma lista fechou o rodapé de Rotas e atalhos, que agora diz que ler o
  arquivo não aplica nada.
- Deployado em `a2d2ea3` no Pi e no moya; conferido autenticado nos dois.
- `515 passed` e bancada `linux2024` verde nos dois perfis com
  `/sistema/config/` e `/sistema/rotas/` no smoke.

## Estado

Concluído em 2026-11-15.
