# Página dos locais de configuração

## Objetivo

Página somente leitura em Sistema que mostra o comando SSH em destaque e o caminho absoluto dos arquivos `.env` e `.ini`. O mesmo código cobre o Pi e o moyaserver. Não há editor no painel.

## Escopo

- Rota `/sistema/config/`, item no menu Sistema, ajuda e `docs/SISTEMA.md`.
- `SSH_LOGIN` e os caminhos de exibição no `host.env` de cada perfil e no Compose.
- Testes de view nos dois perfis.

Fora: gravar arquivo pelo agente, editar conteúdo na UI, deploy no Pi.

## Decisões

- A página não grava nada. O admin copia o SSH e edita no host.
- `SSH_LOGIN` no `host.env`:
  - Pi: `conrado@homelab.local`
  - moya: `conrado@10.72.60.181`
  - Vazio: `ssh` + `SHARE_OWNER` + hostname que o agente já devolve.
- Caminhos mostrados são os do host, não os de dentro do container (`/app/data` não aparece).
- Arquivos nos dois hosts:
  - `/etc/homelab-storage-admin/host.env` — perfil. Vale depois de `install-agent.sh` e `deploy.sh`.
  - `/opt/stacks/homelab-storage-admin/.env` — segredo do Django. Vale depois do `deploy.sh`.
  - `services.ini` em `DATA_DIR` do host — Pi: `/mnt/nas/apps/homelab-storage-admin/data/services.ini`; moya: `/opt/stacks/homelab-storage-admin/data/services.ini`. Vale ao recarregar a página.
- Só no moya, quando `CREDENCIAIS_ENV` está definido: `/home/conrado/moya_credenciais_app/.env`. No Pi a linha não aparece.
- O Compose repassa `SSH_LOGIN`, o caminho de host do `services.ini`, o `.env` do painel e `CREDENCIAIS_ENV` como texto. Não altera `DATA_DIR` dentro do container.
- UI: `page-head`, `card`, `pre`/`mono`, `table-wrap`, `alert`. Português. Sem estilo inline.

## Passos

- [x] Settings, exemplos `host.env` e `docker-compose.yml`.
- [x] View, template, menu, ajuda.
- [x] Testes: Pi sem linha do Credenciais; moya com essa linha e outro SSH; rota na ajuda e no acesso sem login.
- [x] Docs: `docs/SISTEMA.md`, `docs/CONTEXTO.md`.
- [x] `uv run pytest`. Laboratório da VM não entra: a página não mexe em Samba, Btrfs nem disco.
- [ ] Commit e `git push` para `main`. O `deploy.sh` só puxa `main`. WIP alheio (cloudflared, REDE, SEGURANCA, services.ini, plano do Cockpit) fica de fora.

## Verificação

- Pytest local verde nos testes novos e na suíte.
- Não declarar laboratório de VM.

## Estado

2026-11-08: implementação concluída; pytest 375 passed + 7 skipped, 1 falha
pré-existente (`test_services.py::test_example_has_current_pi_services`, cockpit
no `services.ini.example` WIP). VM não rodada. Aguardando commit/push.
