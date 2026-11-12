# Dashboard em blocos condensados

## Objetivo

Reduzir o dashboard a blocos de informação: resumo no topo, saúde em tiles,
discos/backups/shares condensados com detalhe ao abrir, e atalhos de serviço no
rodapé em vez do meio da página.

## Decisões

- **Resumo no topo** (`dash-summary`): seis blocos com um número e uma nota
  curta — saúde, volumes, discos, snapshots, backups e shares. Cada bloco leva
  à seção (`#saude`, `#volumes`) ou à página específica.
- **Saúde em tiles** (`health-grid`): um bloco por aviso, com nível, título e
  detalhe. Sem tabela de duas colunas ocupando a largura toda.
- **Discos em cards** (`details.disk-card`): nome, estado, tamanho, temperatura
  e SMART no resumo; ao abrir, partições, montagens e uso. O botão leva para a
  página Discos.
- **Backups e shares em cards**: contagem, agenda/keep e últimos estados. As
  tabelas completas continuam nas páginas Backups e Shares.
- **Serviços no rodapé**: `base.html` ganhou `.app-footer` com a marca e os
  atalhos do `services.ini`, separado do menu lateral. O dashboard não repete a
  grade de serviços.
- **Shares sem medição no dashboard**: o tamanho assíncrono continua só na
  página Shares, com o mesmo cache do agente.

## Testes

- `test_dashboard_mostra_saude`: resumo + rodapé.
- `test_dashboard_saude_em_blocos`: tiles de alerta.
- `test_dashboard_servicos_ficam_no_rodape`: classes do rodapé.
- `test_saude_usa_blocos_com_pilula`: substitui a antiga tabela.
- `test_dashboard_mostra_uso_por_slice`: disco em card com detalhe.
- `test_dashboard_lista_jobs_de_arquivos`: card de backup com agenda/status.
