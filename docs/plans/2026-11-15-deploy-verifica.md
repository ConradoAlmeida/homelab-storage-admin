# Deploy que confere o que fez e cobra o que ficou pendente

## Objetivo

O `deploy.sh` era "dispare e reze": fazia pull + build + recreate e terminava com
`docker compose ps`, sem verificar se o app respondeu e sem mencionar que uma
mudança no `apps.env` só vale depois de `apps-sync --apply`. O CI também não
guardava dois erros silenciosos do dia a dia: `kit.css` esquecido (a mudança de
CSS não aparece) e modelo alterado sem migração (a coluna nunca é criada).

## Escopo

- Entra: health check no fim do deploy, aviso do `apps.env` pendente com o
  comando pronto por perfil, dois steps no CI e docs.
- Não entra: rodar `apps-sync --apply` de dentro do deploy (precisa de sudo e a
  aplicação é decisão do dono), `--doctor --fix` e deploy único dos dois hosts.

## Decisões

- **Deploy só é verde se `/login/` responder.** É a mesma checagem que o smoke
  da bancada já fazia depois do deploy; agora o próprio script espera (até 90 s)
  e sai 1 com o comando de `logs` na mão. Um container em crash loop deixa de
  passar como sucesso.
- **Pendência do env é medida por data, não por conteúdo.** `apps.env` mais novo
  que `/var/lib/homelab-storage-admin/apps.aplicados` = pull feito, `--apply`
  não. Sem parse duplicado do env em bash e sem falso positivo quando o pull não
  toca no arquivo (git não reescreve arquivo inalterado).
- **`--perfil moya` só onde o script não assume o perfil**, como na UI: o
  `apps-sync` assume `pi`, então o comando do aviso sai limpo no Pi.
- **CI guarda, não conserta**: `tailwind build` + `git diff --exit-code` e
  `makemigrations --check --dry-run`. A versão do CLI é fixa
  (`TAILWIND_CLI_VERSION = 4.1.16`), então a saída é determinística.

## Passos

- [x] 1. `deploy.sh`: health check com retry em `/login/`, falhando o deploy.
- [x] 2. `deploy.sh`: aviso `apps.env` pendente (env mais novo que o estado) com
      o comando `--apply` do perfil.
- [x] 3. CI: `kit.css` recompilado e migrações em dia.
- [x] 4. Testes de layout/CI para os três guardas.
- [x] 5. Docs (`ROTINAS`, `INSTALACAO`) e `CONTEXTO`.
- [x] 6. Deploy nos dois hosts, conferindo as mensagens; bancada nos dois perfis.

## Verificação

- `./deploy.sh` termina com `OK: http://…/login/ -> 200`.
- Com `apps.env` mais novo que o estado, o deploy imprime o `--apply` do perfil
  certo; depois do `--apply`, o aviso desaparece.
- Alterar `frontend/src.css` sem recompilar quebra o CI; `manage.py
  makemigrations --check` falha se faltar migração.
- `pytest` verde e bancada `linux2024` verde nos dois perfis.

## Resultado

- `deploy.sh` termina com `OK: <url>/login/ -> 200` depois de esperar o
  entrypoint; sem resposta, sai 1 com o comando de `logs`. Conferido nos dois
  hosts (Pi em `192.168.0.150:8060`, moya em `127.0.0.1:8060`).
- Aviso do `apps.env` pendente com o comando do perfil; depois do `--apply` o
  aviso some (0 ocorrências no deploy seguinte do moya; mtime conferido no Pi).
- CI: `Migracoes em dia` e `CSS do kit compilado` no run de `788bfe1`, ambos
  verdes; sem recompilar o `src.css`, o `git diff --exit-code` reprova (testado
  localmente, rc=1).
- `521 passed` local e bancada `linux2024` verde nos dois perfis, com o smoke
  passando pelo `deploy.sh` novo (`login respondeu: 200`).

## Estado

Concluído em 2026-11-15.
