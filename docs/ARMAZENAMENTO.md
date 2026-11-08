# Snapshots, discos e Samba

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Backups](BACKUPS.md) · [Arquitetura](ARQUITETURA.md)

> Snapshots Btrfs/rsync, downloads para o Jellyfin, histórico read-only, discos/SMART e shares Samba.

---

## Snapshots

- **Política:** em Snapshots, **Nova política** configura um share que ainda
  não tem. **Editar política** muda quantas versões manter e ativa ou desativa.
  Desativar não apaga os snapshots. Na criação dá para gerar o primeiro snapshot
  na hora.
- **Manual:** botão “Criar snapshot agora” na tela Snapshots, para shares com
  política ativa.
- **Diário:** `homelab-storage-snapshot.timer` roda às 03:00 e cria um snapshot
  para cada share com política ativa.
- **Retenção:** campo `keep` da política (padrão 7).
- **Backend:** `auto` usa Btrfs quando o filesystem é Btrfs; senão usa `rsync`.
  `SNAPSHOT_BACKEND=btrfs|rsync|none` força o modo.
- **Btrfs:** snapdir em `SNAPSHOT_ROOT/<share>`, `btrfs subvolume snapshot -r`.
- **rsync:** snapdir em `<path>/.snapshots`, `rsync -aHAX --link-dest` com
  hardlinks; exclusão de `.snapshots` evita recursão.
- **Tamanho:** Btrfs usa `btrfs filesystem du` (aproximado por extents
  compartilhados). rsync usa live sem `.snapshots` + extra = `du(share) - live`.
- **Restauração:** na página Snapshots, **Restaurar** devolve o snapshot para o
  share com `rsync --delete`, depois de digitar o nome `@GMT-...`. O histórico
  continua só leitura (navegar e baixar). A aba Versões anteriores do Windows
  segue disponível.

No backend Btrfs o share **nasce subvolume** ao ser criado, mesmo sem política
de versões; a política pode ser ligada depois na tela Snapshots. Se a pasta
ainda for diretório comum (criada antes dessa regra), a ativação pede o nome
do share para converter em subvolume, preservando os arquivos. O
`STORAGE_ROOT` precisa estar montado; se o mount cair, o agente aborta em vez de
escrever no microSD. No backend rsync não há essa exigência, mas o path precisa
estar dentro de um prefixo permitido.

### Downloads para o Jellyfin

A página **Torrents** só aparece quando o container `jellyfin` existe. Ela lê
as bibliotecas em `/config/root/default/*/options.xml` (no Pi, Filmes e Séries)
e traduz o caminho do container para o diretório do host. O destino não é livre:
só uma dessas pastas.

O download roda no container `qbittorrent` do overlay do homelab
(`lscr.io/linuxserver/qbittorrent`), na rede do Pi (`network_mode: host`).
Assim o handshake dos peers sai pela interface do host, sem o NAT da bridge.
A WebUI escuta na `8090` e o painel chega nela pelo nome `qbittorrent`. A
`8080` do Pi não é usada por esse container. O UFW, quando está ativo, libera
`6881/tcp` e `6881/udp` para os pares e a `8090/tcp` só a partir de
`172.16.0.0/12`. O UPnP fica ligado para o roteador abrir o retorno. O celular
usa a página Torrents; o arquivo segue para a pasta com o computador desligado.
A tabela de andamento fica no centro da página. Chips filtram o estado; a busca e a pasta ficam numa linha abaixo. **Atualizar** busca só o andamento; **Automático** liga ou desliga a atualização a cada cinco segundos (preferência nesta aba). Adicionar torrent e a API de envio abrem por botões na própria página. O clique na coluna ordena.
Sem o container, a página explica o motivo e não oferece o formulário.

A API de envio usa o mesmo caminho. `POST /api/torrents/` e
`GET /api/torrents/bibliotecas/` exigem `Authorization: Bearer ...`. O token
fica legível no banco do painel. `TORRENT_API_TOKEN` no `host.env` só grava
esse valor na primeira vez, se a linha ainda não existir. Sem token, a página oferece **Criar token**. Com token, a troca é na página
Torrents, com a senha do administrador, e vale na hora. O mesmo registro
aparece em `/admin`, como Token da API de torrents. Rebuild do container
não desfaz a troca. Sessão do painel e token na query não autorizam. O corpo
é JSON com `magnet` e `library` (id ou nome da biblioteca, por exemplo
`Filmes`). O corpo JSON vale também quando o curl manda `-d` com o
content-type de formulário. Sucesso é `201` com o nome da biblioteca. Magnet
inválido ou pasta fora do Jellyfin é `400`. Hash que o qBittorrent já tem na
lista é `409` com `torrent já existe na lista`. Agente ou qBittorrent parado é
`503`. Token vazio ou host sem Jellyfin é `404`.

A categoria gravada no qBittorrent é sempre `jellyfin`. **Organizar biblioteca**
lista pastas fora do padrão Título (Ano), organiza só as marcadas e mostra feito,
não feito e ignorados. Colchetes de release saem do título limpo; o alvo continua
Título (Ano). Pasta sem ano no título (sem override manual) recebe a tag **sem ano**
e não é movida. Pasta grande sem torrent aparece como **Resíduo grande, sem torrent**;
se marcada e com ano no alvo, a mesclagem segue e o aviso permanece no card.
Torrent em movimentação ou verificação não aceita Remover nem Apagar arquivos.
Pasta com torrent ativo fica ignorada até sair da lista do qBittorrent (manter arquivos);
pasta solta mescla no host pelo agente. Na LAN o Caddy
publica `https://homelab.conradhub.com` e o token
segue no header. TLS interno no Caddy fecharia esse trecho.

```bash
curl -X POST https://homelab.conradhub.com/api/torrents/ \
  -H "Authorization: Bearer $TORRENT_API_TOKEN" \
  -d '{"magnet":"magnet:?xt=urn:btih:...","library":"Filmes"}'
```

A lista mostra a taxa de download. **Atualizar** mexe só no andamento; **Automático** controla a busca periódica nesta aba. Pausar e retomar valem enquanto o arquivo baixa. No torrent concluído esses
botões somem; **Remover** tira o item da fila e o arquivo permanece. **Apagar arquivos** pede
confirmação e só vale para um torrent cuja pasta está dentro de uma biblioteca.
Enquanto o qBittorrent está em movimentação ou verificação, Remover e Apagar arquivos
somem e a linha exibe o aviso para aguardar o estado estabilizar.
A pasta da biblioteca não é removida.

---

### Histórico (read-only)

`/history/` navega os shares e snapshots `@GMT-...`:
- live e cada snapshot, com breadcrumb;
- lista de pastas/arquivos, paginação e download;
- busca no snapshot inteiro por nome/caminho, sem diferenciar maiúsculas;
- resultados com abrir pasta, baixar e “Versões”;
- “Versões” por arquivo, comparando live + snapshots;
- tudo somente leitura neste navegador; restore do share fica em Snapshots.

Na tela **Snapshots**, cada snapshot tem o botão **Navegar**, que abre esse
navegador já no snapshot escolhido. A busca é feita no conteúdo do snapshot
selecionado; não altera nem cria arquivos.

O container precisa do `STORAGE_ROOT` montado read-only (no Pi, `/mnt/nas`;
no moya, `/srv/samba` e `/mnt/data`). No Pi, `/mnt/jellyfin` também é montado
read-only para o share `jellyfin` aparecer no histórico; sem esse mount, a rota
`/history/jellyfin/live/` retorna 404. O app não escreve nos dados por esse
caminho; qualquer escrita continua no agente root.

## Discos e SMART

`/storage/` mostra:
- temperatura da CPU, fans/PWM (quando expostos), load e RAM;
- total/uso/livre somando os volumes monitorados e um cartão por volume;
- cada disco (`sda`, `sdb`, `sdd`, `mmcblk0`), modelo, serial, tamanho, montagem, uso e estado;
- temperatura **somente se o disco já estiver ativo**;
- RAID (`/proc/mdstat`, `mdadm --detail`) e Btrfs (usage, device stats, scrub).

A coleta de **discos/SMART/RAID/Btrfs** é **diária**
(`homelab-storage-metrics.timer`, 06:00) e fica em cache; o dashboard e
`/storage/` não executam `smartctl` no request. O botão **Atualizar agora**
força uma coleta. Disco em standby não é acordado.

As métricas de **hardware do Pi** (CPU %, temperatura da CPU, load, RAM e fans)
têm um endpoint próprio, `/metrics/live/`, consultado a cada 1 s pelo
frontend. Ele lê apenas `/proc` e `/sys`, não chama `smartctl`/`lsblk`/`df` e
pausa quando a aba está oculta. Temperatura/uso de disco continuam no cache.

Regras de standby:
- o agente usa `hdparm -C` para o estado e `smartctl -n standby` para temperatura/SMART;
- se o disco estiver em `standby`/`sleeping`, o comando retorna sem acordar;
- “Ler SMART” é um POST explícito e também respeita standby;
- testes **curto/longo** só por botão; o longo pede confirmação e pode demorar horas;
- a página não inicia teste nem SMART completo sozinha.
- No **Active Cooler oficial**, `0 rpm` com `PWM 0%` significa fan parado; a curva começa por volta de 50 °C. A UI mostra o zero explicitamente, em vez de “—”.

## Samba

O app escreve seções no `/etc/samba/smb.conf`, roda `testparm -s` e recarrega
com `smbcontrol smbd reload-config`. Se a configuração for inválida, restaura o
backup `.bak-AAAAMMDD-HHMMSS`.

Cada share novo cria os grupos `<share>`, `<share>_ro` e `<share>_rw`, com
permissões `2775`. O dono padrão é `conrado` (ajustável em
`SHARE_OWNER` no service do agente). O checkbox **Privado** adiciona
`browseable = no`; a restrição real continua sendo o grupo `<share>_rw`
(adicione só o dono nele).

**Usuários → Novo grupo** cria um grupo Linux/Samba com nome validado e GID
opcional (1000–60000). O agente bloqueia grupos reservados, grupos existentes e
GIDs em uso; não há renomear/excluir pela UI.

Senhas do Linux e do Samba são independentes. O painel cria a conta Linux sem
senha e com shell `/usr/sbin/nologin` e define só a credencial Samba
(`smbpasswd`, por stdin); não há `unix password sync`. Rodar `passwd usuario` no
servidor cria uma senha Unix que não acompanha a do Samba, e vice-versa. O
painel não guarda a senha em texto: esquecida, o caminho é definir outra.

Para gerenciar senhas Samba fora do app: `sudo smbpasswd -a usuario`.

Descoberta na LAN (Nautilus vs Windows): [Nomes na LAN](REDE.md#nomes-na-lan).
