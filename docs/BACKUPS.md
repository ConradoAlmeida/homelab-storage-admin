# Backups

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Snapshots e discos](ARMAZENAMENTO.md) · [Instalação](INSTALACAO.md)

> Preparação de disco, jobs restic, snapshots, backup local, cópia fria USB e backup do Gitea/Credenciais.

---

## Preparação de disco

`/backups/` começa pelo wizard de disco:
- lista discos com modelo, serial, tamanho, filesystem/label, montagem e se já há backup;
- recusa disco do sistema, membro de RAID, montado ou com holders;
- disco vazio pede `FORMATAR /dev/sdX`;
- disco com **filesystem existente** (mesmo vazio) pede **aviso extra** + `APAGAR /dev/sdX`;
- disco já configurado pede **aviso extra** + `RECONFIGURAR /dev/sdX`;
- o destino é mostrado como **ext4 (recomendado)**; nesta versão é fixo em ext4;
- sempre exige a senha do app;
- o agente revalida estado, frase e `allow_existing` antes de qualquer `wipefs`.

O wizard formata ext4, cria entrada no fstab por UUID, monta em
`/mnt/backup/<label>`, inicializa o restic e mostra a senha de recuperação.
A senha fica em arquivo root-only em `/etc/homelab-backup/secrets/` e também
pode ser consultada em **Backups → Senha do repositório**, mediante a senha do app
(com registro no audit log). O submit só dispara: o agente valida a frase,
grava o status e o systemd formata/monta/inicializa. A página consulta esse
status até concluir ou falhar e então mostra a senha. O Gunicorn espera no
máximo 660 s, o bastante para download e busca.

O disco preparado fica registrado em `/etc/homelab-backup/config.json`; o
cadastro de jobs usa esse registro na [Jobs de backup](#jobs-de-backup).

## Jobs de backup

`/backups/jobs/new/` e `/backups/jobs/<nome>/edit/` configuram:
- nome do job e disco de destino;
- fontes (shares) e exclusões (`--iexclude`, case-insensitive);
- exclusões **pré-preenchidas** com temporários, locks, downloads parciais e backups auxiliares de CAD/design (SolidWorks, Blender, FreeCAD, Inkscape, GIMP, Krita, AutoCAD, SketchUp, Rhino, InDesign); os arquivos reais não entram na lista; botão **Restaurar lista padrão**; `.snapshots` também fica de fora;
- periodicidade **diário**, **semanal** ou **mensal**, com horário;
- retenção diária/semanal/mensal;
- ativo/desativado.

Ao salvar, o agente grava o job em `/etc/homelab-backup/config.json` e cria/atualiza
um timer systemd `homelab-restic-backup-<job>.timer`. O serviço
`homelab-restic-backup@<job>.service` executa
`/usr/local/sbin/homelab-restic-backup <job>` como root.

O executor:
- valida mountpoint, repo e senha root-only;
- roda `restic backup` com as fontes e exclusões;
- aplica `forget --keep-daily/--keep-weekly/--keep-monthly --prune`;
- grava status em `/etc/homelab-backup/status/<job>.json` e log em
  `/var/log/homelab-restic/<job>.log`;
- usa cache do restic no próprio disco de backup (`.restic-cache`).

Na tela de jobs: **Rodar agora** (systemd, sem bloquear a requisição),
**Ativar/Desativar**, **Editar** e **Excluir** (o repositório restic é mantido).
A tabela mostra último status e próxima execução.

### Snapshots restic

**Backups → Snapshots restic** lê `restic snapshots --json` de cada disco
configurado e mostra disco, ID curto, data, arquivos, tamanho, bytes
adicionados e fontes. Snapshots vazios aparecem marcados; a retenção é aplicada
pelo job, não por essa tela.

O botão **Navegar** abre um navegador read-only do snapshot:

- lista pastas e arquivos com tamanho, data de modificação e permissões;
- navega por breadcrumb sem restaurar nem sobrescrever shares;
- **Buscar** procura no snapshot inteiro por trecho de nome/caminho, sem diferenciar maiúsculas; aceita `*` e `?` como curingas;
- resultados mostram caminho, tipo, tamanho e data, com atalho para abrir a pasta ou baixar o arquivo;
- a busca é limitada aos primeiros 200 resultados, mas informa o total encontrado;
- **Baixar** usa `restic dump` no agente e o app serve o arquivo em streaming;
- o download temporário fica em `DOWNLOAD_DIR` (padrão `DATA_DIR/downloads`) e
  é limpo depois de 24 h;
- caminhos, snapshot e disco são validados no agente; não há shell livre.

Restaurar uma árvore inteira para um share continua sendo uma operação manual
via CLI; o navegador serve para inspecionar e baixar itens específicos.

## Backup local de arquivos

**Backups → Backup de arquivos** cria **jobs independentes**, cada um com suas
fontes, periodicidade e retenção. Sem restic; leitura restrita ao root.

- **Job**: nome (a-z, 0-9, _, -), rótulo, fontes (um caminho por linha),
  diário ou semanal, dia da semana, horário, retenção em dias e ativo/inativo.
- **Fontes**: arquivo ou pasta, caminho absoluto, até
  CREDENCIAIS_MAX_SOURCE_BYTES (2 GB). Symlinks, pastas especiais e /proc,
  /sys, /dev, /run são recusados. O banco e o .env do Credenciais são
  reconhecidos pelo caminho e copiados com segurança (SQLite backup API).
- **Agendamento**: um timer systemd por job
  (homelab-arquivos-backup-<job>.timer) e o serviço
  homelab-arquivos-backup@<job>.service. Alterar o job reescreve o
  OnCalendar; jobs desativados têm o timer removido.
- **Pacote**: <job>-AAAAMMDD-HHMMSS.tar.gz em CREDENCIAIS_BACKUP_DIR, com
  manifest.json, arquivos 600 root:root e pasta 700. Pastas preservam a
  estrutura interna, inclusive vazias.
- **Status**: /etc/homelab-backup/status/<job>.json, com último resultado,
  próxima execução e lista de pacotes por job.
- **Restore**: extrai em staging, confere sha256 e PRAGMA integrity_check
  quando há banco; copia o estado atual para pre-restore-AAAAMMDD-HHMMSS;
  devolve tudo ao caminho de origem com dono/permissão originais e reinicia o
  container quando o banco do Credenciais é restaurado. Não apaga arquivos
  criados depois do backup.
- **Download** usa o diretório temporário do restic e é auditado.

A configuração fica em `/etc/homelab-backup/credenciais.json` (jobs com
`name`, `label`, `enabled`, `sources`, `frequency`, `weekday`, `time` e
`retention_days`). O formato antigo (job único com `files`) é migrado
automaticamente para o job `credenciais`.

## restic e disco externo

O módulo restic é o caminho para pastas grandes. Ele só é habilitado quando
existe um **disco externo** disponível:

- O wizard **recusa** o disco do sistema/dados (`/`, `/boot`, `/mnt/data`).
  Repositório no mesmo disco físico não protege contra falha de disco.
- Sem disco externo, jobs restic gravam status **`skipped`** ("aguardando
  disco") em vez de falhar; o backup local de arquivos continua ativo.
- Com um disco: repositório restic nele. Com dois: repositório no disco A e
  **cópia fria** no disco B.
- Senha do repositório em `/etc/homelab-backup/secrets/<uuid>.key`
  (`600 root`). Guarde uma cópia offline: sem ela o backup é irrecuperável.
- **Verificação semanal** (`homelab-restic-check.timer`, domingo 04:30) roda
  `restic check --read-data-subset=2%` e grava
  `/etc/homelab-backup/health/<uuid>.json`; a página de Backups mostra o último
  check e tem o botão **Verificar repo**. Se o check achar um lock deste host
  cujo PID já não existe, o agente remove o lock velho e tenta de novo.
- **Restore:** na lista de snapshots restic, **Restaurar** devolve os caminhos
  originais (ou um arquivo/pasta na navegação). Pede o identificador do
  snapshot. Não restaura na raiz do sistema nem no disco de backup.

## Backup do Gitea

**Backups → Backup do Gitea** gera um dump consistente e permite copiá-lo
manualmente para um drive USB. O Gitea continua rodando durante o dump.

- **Dump**: `gitea dump` executado como usuário `git` dentro do container,
  com `--skip-log --skip-index`. O zip é copiado para
  `/var/backups/gitea/gitea-AAAAMMDD-HHMMSS.zip`, `600 root`, com `sha256`
  registrado. Mantém os últimos `GITEA_KEEP` dumps (padrão 2).
- **USB**: a tela lista drives removíveis (USB), mostra filesystem, rótulo e
  espaço livre. O backup monta o drive (se preciso), confere o espaço, copia
  para `<drive>/gitea/<zip>` + `.sha256`, confere o hash e desmonta.
  Arquivos existentes no drive não são apagados; nada é formatado.
- **Status**: `/etc/homelab-backup/gitea.json` (`dump`, `usb`, `done`,
  `failed`), exibido na própria página. O dump continua no servidor mesmo se a
  cópia para o USB falhar.
- **Execução assíncrona**: `homelab-gitea-backup@<host|device>.service`, então
  a página não fica presa durante os ~3,7 GB.
- **Restauração**: na lista de dumps, **Restaurar** para o container (só existe
  se o Gitea estiver neste host). O agente para o container, copia o volume
  para `gitea-pre-restore-...`, aplica `app.ini`, custom, data, sqlite e
  repositórios, e sobe o Gitea. Pede o nome do zip. Dump SQL de Postgres fica
  copiado em `gitea-db.sql` no volume para import manual.

> O fluxo **dump + cópia para pendrive** foi validado manualmente. Não é
> necessário repetir o teste enquanto o código de dump/cópia USB não mudar.

O backup do Gitea é **manual por decisão** (dump + USB). Quando houver
repositório restic, a pasta `/var/backups/gitea` pode entrar em um job restic
para versionamento e cópia fora do disco.
