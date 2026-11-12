# Dashboard em blocos condensados

## Objetivo

Reduzir o dashboard a blocos de informação: resumo no topo, saúde em tiles,
discos/backups/shares condensados com detalhe ao abrir, e atalhos de serviço no
rodapé em vez do meio da página.

## Decisões

- **Resumo no topo** (`stat-grid`): seis blocos com um número e uma nota
  curta — saúde, volumes, discos, snapshots, backups e shares. Saúde abre a
  página dedicada; Discos, Snapshots, Backups e Shares abrem a página
  específica. Volumes é só indicador, sem scroll interno.
- **Página Saúde** (`/saude/`): alertas do agente em tiles (`tile-grid`) e
  volumes do host. O card de Saúde do dashboard leva para lá; o menu Sistema
  também.
- **Discos em cards** (`details.disk-card`): nome, estado, tamanho, temperatura
  e SMART no resumo; ao abrir, partições, montagens e uso. O botão leva para a
  página Discos.
- **Backups e shares em cards**: contagem, agenda/keep e últimos estados. As
  tabelas completas continuam nas páginas Backups e Shares.
- **Serviços no rodapé**: `base.html` ganhou um rodapé fixo com a marca e os
  atalhos do `services.ini` como botões, separado do menu lateral. O dashboard
  não repete a grade de serviços; o rodapé garante que os atalhos fiquem
  visíveis sem rolar até o fim.
- **Shares sem medição no dashboard**: o tamanho assíncrono continua só na
  página Shares, com o mesmo cache do agente.

## Testes

- `test_dashboard_mostra_saude`: resumo com link para `/saude/`.
- `test_dashboard_saude_em_blocos` e `test_saude_usa_blocos_com_pilula`:
  tiles na página Saúde.
- `test_saude_pagina_mostra_volumes`: volumes na página Saúde.
- `test_dashboard_servicos_ficam_no_rodape` e
  `test_rodape_mostra_servicos_como_botoes`: rodapé fixo com botões.
- `test_dashboard_mostra_uso_por_slice`: disco em card com detalhe.
- `test_dashboard_lista_jobs_de_arquivos`: card de backup com agenda/status.
