# --doctor no fim do deploy

## Objetivo

O `--doctor` só era rodado quando alguém lembrava, e o deploy não olhava a
ponta das rotas: um `apps.caddy` editado à mão, um `services.ini` apagado ou um
upstream errado só apareciam na próxima vez que alguém digitasse o comando.
Como o `--doctor` é read-only e roda sem sudo nos dois hosts (só a validação do
TLS com o token da Cloudflare pede root, e vira aviso), ele pode entrar no
deploy.

## Escopo

- Entra: rodar `--doctor` no fim do `deploy.sh`, com o `--perfil` do host, e
  imprimir erros + resumo. Falha do doctor **não** reprova o deploy.
- Não entra: `--doctor --fix`, timer diário (resultado iria para o journal, que
  ninguém lê) e rodar o doctor com sudo dentro do deploy (no Pi o sudo pede
  senha e o deploy roda como usuário comum).

## Decisões

- **Só informa.** O contrato do deploy continua sendo "o app respondeu"
  (`/login/`). Reprovar por desvio de rota puniria um deploy correto por um
  problema pré-existente — e o texto do `AVISO` já diz que o app está no ar.
- **Só `erro:` sai na saída.** No Pi o aviso do token da Cloudflare aparece em
  toda execução; o resumo (`erros: N; avisos: M`) já dá o número.
- **Roda sem sudo.** Caddyfile é 0644 e o DNS/estado são legíveis; o que exige
  root (validar TLS com o token) degrada para aviso, documentado.
- **Sem env não roda.** `APPS_ENV_PATH` vazio ou arquivo ausente: o doctor seria
  o do perfil errado, então o bloco é pulado.

## Passos

- [x] 1. `APPS_PERFIL` calculado uma vez (serve ao aviso e ao doctor).
- [x] 2. Seção `==> rotas, DNS e atalhos (--doctor)` no fim, com `set +e`
      para o exit code do doctor não derrubar o deploy.
- [x] 3. Teste de layout garantindo que o doctor entrou e que não há `exit 1`
      depois dele.
- [x] 3b. Re-exec depois do pull quando o `deploy.sh` mudou: bash lê o script
      por offset e o deploy que se atualiza roda o tail antigo (aconteceu na
      primeira execução com o doctor).
- [ ] 4. Deploy nos dois hosts e conferência da seção nova.
- [ ] 5. Docs e bancada.

## Verificação

- `./deploy.sh` no Pi e no moya termina com `OK: …/login/ -> 200` seguido de
  `==> rotas, DNS e atalhos (--doctor)` e `erros: 0`.
- Com um erro forçado no doctor, o deploy continua saindo 0 e imprime o
  `AVISO` + o comando para ver o detalhe (simulado localmente com stub).
- `pytest` verde e bancada nos dois perfis.

## Estado

Em andamento em 2026-11-15.
