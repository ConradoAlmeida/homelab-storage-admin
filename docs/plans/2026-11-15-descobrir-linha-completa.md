# --descobrir sugere a linha completa

## Objetivo

O fluxo "subi um container, quero expor" ainda era manual: descobrir a porta, o
nome, escrever a linha e só depois decidir `atalho=`. O `--descobrir` já
encontrava a stack fora do env, mas imprimia só `key|fqdn|127.0.0.1:porta|dir|`
— sem atalho, sem grupo, e com um upstream que não existe no Pi (lá o Caddy
fala com a LAN, não com o loopback).

## Escopo

- Entra: flags de apresentação na sugestão, upstream por perfil, escolha da
  porta quando o container publica várias, notas de revisão, testes e docs.
- Não entra: aplicar a sugestão (continua sendo revisar + commitar + `--apply`),
  descobrir `descricao=`/`cor=` (não há de onde tirar) e casar uma stack nova
  com uma app já declarada que tem `dir=-` (fica no backlog).

## Decisões

- **Atalho já vem escolhido, mas é sugestão.** No moya o portal é o hub do host
  (11 de 12 apps), então `atalho=portal`; no Pi o painel é o único consumidor,
  então `atalho=painel`. Sem `atalho=` a app não aparece em lugar nenhum — por
  isso o default da sugestão não é "nenhum", e a nota lembra as opções.
- **`icone=` e `grupo=` só onde têm efeito.** O painel ignora os dois; fora do
  moya a sugestão sai sem eles. `icone=` usa a própria key (slug válido); sem
  SVG no portal, o card cai na inicial.
- **Upstream do perfil, não `127.0.0.1` fixo.** Pi: `192.168.0.150` (o mesmo
  `DNS_IP` que o env usa); moya: `localhost` (os compose publicam em loopback).
- **Porta: prefere HTTP.** `docker port` devolve tudo o que o container publica
  — o Pi-hole publica 53, e sugerir `…:53` como upstream de site era um erro
  silencioso. A escolha passa por 443/80/8080/8000/3000/5000/9000, depois a
  primeira acima de 1024, e a saída diz quais portas existem.
- **Nada é escrito.** A aprovação continua sendo revisar a linha no repo,
  commitar e rodar o `--apply`.

## Passos

- [x] 1. `UPSTREAM_HOST` por perfil e `nome_de_fqdn` reaproveitado.
- [x] 2. Sugestão com `atalho=`/`nome=` (e `icone=`/`grupo=` no moya) + notas
      de revisão no resumo.
- [x] 3. Escolha de porta por heurística HTTP, com aviso quando há várias.
- [x] 4. Testes: moya com flags e `localhost`, Pi com `192.168.0.150` e sem
      `grupo=`, container com 53/22/8888 escolhendo 8888.
- [x] 5. Docs (`REDE`, `ROTINAS`, ajuda do script) e este plano.
- [ ] 6. Bancada nos dois perfis.

## Verificação

- `--descobrir` no moya imprime a linha com `atalho=portal,icone=…,grupo=…` e
  `localhost:porta`; no Pi, `atalho=painel` e `192.168.0.150:porta`.
- Nada no env, no Caddy ou no DNS muda depois de rodar o comando.
- `pytest` verde (43 testes do reconciler) e bancada nos dois perfis.

## Estado

Implementado em 2026-11-15; falta bancada.
