# Torrents: seleção indevida e refresh do andamento

## Objetivo

Na página `/torrents`, o bloco de andamento não pode mais nascer com o texto selecionado nem voltar a selecionar tudo sozinho. No mesmo bloco, um botão liga e desliga a atualização automática e outro atualiza só essa parte, sem recarregar a página.

## Escopo

- `static/js/downloads.js`
- `templates/torrents.html`
- `static/css/ui.css` só se o botão pressionado precisar de estado visível com classe já do kit
- `core/ajuda.py`, `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md`
- asserções em `tests/test_views.py` (e ajuda, se o texto estiver fixado no teste)

Fora: agente, qBittorrent, ações de pausar/remover/apagar, deploy, commit.

## Decisões

- A seleção é efeito do DOM, não de CSS. `aplicar()` faz `appendChild` de cada linha visível no carregamento e de novo a cada poll (5 s), mesmo quando a ordem não mudou. O Chromium trata esse desanexar/reinserir como seleção e pinta a tabela inteira (nome, progresso, taxa e botões), como no print. Limpar a seleção dura até o próximo ciclo.
- Só mover uma `<tr>` quando a posição desejada for outra. Antes de escrever texto ou `progress.value`, não fazer nada se o valor já é o mesmo. Se o usuário não tinha uma seleção não colapsada dentro da tabela antes da atualização, `removeAllRanges()` só no caso de a atualização ter criado seleção dentro dela. Seleção que o usuário fez para copiar um nome permanece.
- Acabar com `window.location.reload()` nesse fluxo. `GET /torrents/estado/` já devolve o JSON. A mesma função serve o automático e o botão manual.
- A URL fica em `data-torrent-status` na seção Andamento, também com a lista vazia e com tudo parado. O atributo não é removido quando `active` é falso.
- Cada linha traz os dois forms, Pausar e Retomar. O que não vale fica com `hidden`, conforme `can_pause` / `can_resume`. Mudança de estado só alterna `hidden`, o rótulo e a classe do `.status`. Remover e Apagar arquivos continuam como estão.
- Linha nova sai de `<template id="torrent-linha">` (markup Django, com `{% csrf_token %}`). Hash que sumiu sai do `tbody`. A tabela, os chips e a busca existem mesmo com zero torrents; o vazio é o `[data-torrent-empty]`.
- Botões em `.page-actions` do Andamento, `btn small`:
  - `Atualizar` (`data-torrent-refresh`): uma busca, sem reload. `aria-busy` na seção enquanto a resposta não volta. Pedido em curso ignora o segundo clique.
  - `Automático` (`data-torrent-auto`, `aria-pressed`): liga/desliga o `setInterval` de 5 s. Preferência em `sessionStorage` na chave `torrent-auto` (`"1"` / `"0"`). Sem valor salvo, começa pressionado só quando `overview.active` é verdadeiro.
- Falha de rede ou HTTP deixa a lista como está e escreve o motivo em `[data-torrent-refresh-erro]` (`role="status"`). Sem `alert` de página e sem 500.
- Filtro, pasta e ordem continuam no `sessionStorage` `torrent-tabela`.
- Texto de UI em português. Sem utilitário Tailwind no HTML. Sem commit e sem deploy.

## Passos

- [x] `downloads.js`: reordenar só se a posição mudou; não reescrever texto igual; não recarregar a página; uma função `atualizar()` para o poll e para o botão.
- [x] Template: seção sempre com a URL, os dois botões, a tabela (também vazia), os dois forms por linha e o `<template id="torrent-linha">`.
- [x] Incluir ou tirar linhas pelo JSON; alternar Pausar/Retomar; atualizar tamanho, taxa, progresso, ETA e classe de estado.
- [x] Persistir o automático. Manual funciona com o automático desligado.
- [x] Ajuda do capítulo Andamento, `docs/ARMAZENAMENTO.md` e `docs/CONTEXTO.md`: automático só enquanto o botão está ligado; Atualizar mexe só no andamento.
- [x] `uv run pytest`. A VM não entra: a mudança não passa pelo agente, Samba, restic nem disco.

## Verificação

- Abrir `/torrents/` com torrents ativos: o texto da tabela não está selecionado. Limpar qualquer seleção e esperar mais de 5 s: continua sem seleção.
- Ordenar por download (a ordem muda no poll): a seleção não cobre a tabela.
- Automático desligado: a taxa não muda sozinha. Atualizar: muda só o andamento; painéis, filtros e o restante da página ficam.
- Pausar pela própria linha continua com confirmação onde já existe. Estado que troca Pausar/Retomar não recarrega o documento.
- Lista vazia: Atualizar pode preencher a tabela se o JSON trouxer itens.
- Pytest local verde. Sem virt-manager neste passo.

## Estado

Implementado em 2026-11-04. Pytest: 289 passed, 6 skipped. Browser manual não feito: runserver demo redireciona para login sem credenciais locais.
