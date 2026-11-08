# Share no disco do Jellyfin

## Objetivo

O portal cria um share em `/mnt/jellyfin/fotos` (ou outra pasta desse disco) quando `/mnt/jellyfin` está montado. No ext4 a pasta nasce diretório comum.

## Escopo

- Prefixo efetivo de share no formulário e no agente.
- Texto de ajuda e docs curtos.
- Testes do formulário e do agente.

Fora: backup restic, alterar `host.env` do Pi à mão, snapshot obrigatório.

## Decisões

- `ALLOWED_PATH_PREFIXES` continua sendo a lista base. `JELLYFIN_ROOT` entra só na validação de share, e só se `os.path.ismount` for verdadeiro.
- Sem o mount, o caminho segue recusado. Sem alerta no moya.
- ext4 segue `mkdir`. Btrfs segue subvolume. A caixa de snapshot não muda.

## Passos

- [x] Prefixo no agente e no formulário.
- [x] Testes.
- [x] Docs.
- [x] Pytest local: 371 passed; 1 failed em `tests/test_services.py` por `services.ini.example` alheio (cockpit/dockge), fora desta mudança. Lab da VM não se aplica: não há disco nem Samba novo, só o prefixo quando o mount existe.

## Estado

Implementado. Com `/mnt/jellyfin` montado, o portal aceita `/mnt/jellyfin/fotos` e o agente cria diretório comum.
