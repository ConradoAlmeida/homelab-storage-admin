# Esconder a organização de torrents

## Objetivo

A organização de Séries e Filmes sai do centro da página. Fica atrás de um botão, no mesmo jeito de Adicionar torrent e Configurar API. Listar e organizar continuam iguais.

## Escopo

- `templates/torrents.html`
- `frontend/src.css` e o `static/css/kit.css` gerado por `uv run manage.py tailwind build`
- teste em `tests/test_views.py` e uma linha na ajuda, se o texto disser que a ferramenta está no centro da página

Fora: regra de renomear, agente, deploy, commit.

## Decisões

- Não há página nova. O painel usa o rádio que já existe, com o valor `organizar`.
- O botão **Organizar** fica em `page-actions`, ao lado de Adicionar torrent e Configurar API. Só aparece com cliente qBittorrent e biblioteca.
- O bloco atual (texto, escolha da biblioteca, lista, **Organizar marcadas** e o card Organização) entra em `section.torrent-panel.torrent-panel-organizar`. Fechado, a página mostra só o andamento.
- O rádio `organizar` começa marcado quando a resposta traz a lista (`pastas_fora is not None`) ou o relatório (`organizacao`). Assim o resultado não some depois do POST. Nos outros casos o rádio marcado continua o de hoje.
- O CSS novo fica em `frontend/src.css`, no mesmo `:has()` dos outros painéis, e o `kit.css` é recompilado. Sem utilitário Tailwind no HTML.

## Passos

- [x] Mover o bloco para o painel e acrescentar o botão e o rádio.
- [x] Regra no `src.css` e `tailwind build`.
- [x] Teste: GET comum não marca o rádio; lista ou relatório marca. `uv run pytest`. Sem VM.

## Verificação

Na página de torrents o andamento aparece direto. Organizar abre o painel e fecha Adicionar e API. Depois de listar, o painel continua aberto com a tabela.

## Estado

Implementado em 2026-11-04. Painel `torrent-panel-organizar` com rádio e botão Organizar; CSS no kit; testes em `test_views.py` (71 passed neste arquivo).
