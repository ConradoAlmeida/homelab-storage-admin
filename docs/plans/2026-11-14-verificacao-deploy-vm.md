# Verificação do deploy do `origin/main` no perfil homelab (antes do Pi)

## Objetivo

Validar `origin/main` (`0da95c5`) em Ubuntu 26.04 server-like antes de aplicar
no Pi, com foco no que o pytest local não cobre: agente novo, reescrita do
timer de snapshots e operações systemd/journal/terminal.

## Escopo

- VM `linux2024` (`qemu:///system`, `192.168.122.26`), clone limpo em `~/hsa-main-0da95c5`.
- Não altera `/opt/stacks` do Pi, nem o clone antigo do usuário na VM.
- Não testa hardware real, overlay Jellyfin/qBittorrent, UFW ativo nem `/mnt/nas`.

## Decisões

- Clone novo em vez de mexer no `~/homelab-storage-admin` da VM (árvore suja, `9283d57`).
- `host.env` da VM preservado (o `install-agent.sh` não sobrescreve): reproduz o
  cenário do Pi, com perfil antigo e binário do agente de 31/10.
- Smoke das páginas com o app em container e o socket real do agente.
- Terminal testado por último, com rollback se necessário (só afeta a VM).

## Passos

- [x] 1. Backup na VM: `host.env`, units `homelab-*` e hash do agente atual
      (`/root/pre-deploy-20261115-1401.tgz`).
- [x] 2. Clone limpo de `main` em `~/hsa-main-0da95c5`, `uv sync --dev`,
      `manage.py check` sem issues.
- [x] 3. `pytest` — **453 passed, 8 skipped** (28 s).
- [x] 4. `sudo env HOST_ENV_PROFILE=pi ./install-agent.sh` com `host.env` antigo:
      perfil não sobrescrito, `host.env` com mesmo sha256.
- [x] 5. Timer reescrito para `00:05` e `12:05`, `snapshot-schedule.json`
      (`per_day=2`), sem `/etc/cron.d/samba-snapshots`, agente ativo, socket ok.
- [x] 6. Ops via socket: `host_info`, `journal`, `systemd_list_units` (189 units),
      `ssh_keys`, `apt_check`, `versoes_schedule`, `health_overview` — todas ok.
- [x] 7. `sudo bash scripts/vm/run-lab-tests.sh` — **8 passed**.
- [x] 8. App em container (`hsa-vm`) no perfil homelab: 16 páginas, nenhum 5xx;
      agenda "2×/dia às 00:05 e 12:05" no Dashboard e em Backups; estáticos
      (kit/ui/xterm) 200; terminal abriu pty, executou `id` e fechou, com
      `AuditLog` de `terminal.open`/`terminal.close`.
- [x] 9. Resultado registrado abaixo.

## Verificação

- Nenhum 5xx nas 16 páginas — ok.
- Timer com dois horários e `snapshot-schedule.json` gravado — ok.
- Lab verde (8) e pytest igual ao local (453/8) — ok.
- Pi-safe: `/torrents/` e `/backups/gitea/` redirecionam, `/sistema/admins/`
  mostra "Gestão desativada" com `DJANGO_ADMIN_MANAGE=0` — ok.

## Achados

1. **Terminal depende de senha sudo real.** `_sudo_confere` roda
   `sudo -k -S -v`; em host com `NOPASSWD` a validação sempre falha (o bench da
   VM usa NOPASSWD). No Pi funciona. Testado com usuário temporário com senha
   (criado e removido na sessão).
2. **`createsuperuser --noinput` exige `DJANGO_SUPERUSER_EMAIL`** no Django 5.2
   e o `entrypoint.sh` esconde o erro (`2>/dev/null || true`). O `.env.example`
   já traz a variável; sem ela, instalação nova fica sem admin e sem aviso.

## Estado

Concluído em 2026-11-15. VM `linux2024` ficou com o agente novo e a agenda
2×/dia; o clone antigo `~/homelab-storage-admin` não foi tocado.

Os ajustes levantados aqui viraram o commit `f326e01`
(`fix(deploy): exigir .env, docker e agente completo`): falha cedo sem `.env`
ou sem Docker, compara todos os binários/units do agente, UPnP e config do
qBittorrent viram aviso e o `createsuperuser` deixa de ser silencioso. A
bancada por perfil (limpeza, snapshots e `bench.sh`) segue em
[2026-11-15-bancada-vm-perfis.md](2026-11-15-bancada-vm-perfis.md).
