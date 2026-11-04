# Troubleshooting

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Segurança](SEGURANCA.md) · [Instalação](INSTALACAO.md)

> Sintomas, causas e correções dos problemas mais comuns.

---

| Sintoma | Causa provável | Ação |
|---|---|---|
| “Agente indisponível” | serviço parado ou socket ausente | `sudo systemctl status homelab-storage-agent` |
| `ModuleNotFoundError: No module named 'django'` | rodou `python3 manage.py` no host, fora do venv/container | use `uv run manage.py ...` ou `docker compose exec web ...` |
| `attempt to write a readonly database` | rodou no diretório antigo `~/homelab-storage-admin` ou sem `DJANGO_SQLITE_PATH` | use `/opt/stacks/homelab-storage-admin` e o banco em `/mnt/nas/apps/...`; ou o container |
| `btrfs ... not a subvolume` | share criado como diretório comum | recriar com snapshot marcado |
| `/mnt/nas nao esta montado` | array não montado | `mount /mnt/nas` / conferir `fstab` |
| `testparm` falhou | seção inválida no `smb.conf` | o app restaura o backup; revisar o log |
| Versões anteriores vazias | `shadow_copy2`/`shadow:snapdir` errado | conferir a seção do share e reiniciar o `smbd` |
| `400 Bad Request` no domínio público | hostname fora de `DJANGO_ALLOWED_HOSTS` | acrescentar `homelab.conradhub.com` e rodar `./deploy.sh` |
| `CSRF verification failed` atrás do túnel | origem `https://` fora de `DJANGO_CSRF_TRUSTED_ORIGINS` | acrescentar `https://homelab.conradhub.com` |
| Login ok fora de casa, falha em casa | `DJANGO_SECURE_COOKIES=1` sem HTTPS no mesmo nome | usar `https://homelab.conradhub.com` ou manter `DJANGO_SECURE_COOKIES=0` até o Caddy alinhar ([Cookies e HTTPS](SEGURANCA.md#cookies-e-https)) |
| Troca de senha sem alerta de sucesso/fracasso | POST inválido (campo hidden) ou só o aviso do Chrome em HTTP | a tela mostra `alert`; o log do agente tem `SET_PASSWORD` se gravou. O aviso “Password fields present on an insecure (http://) page” é o Chrome, não o app |
| `502` no `cloudflared` | ingress aponta para porta errada ou Caddy parado | `curl -kI https://192.168.0.150/login/ -H 'Host: homelab.conradhub.com'` no Pi; conferir `deploy/pi/cloudflared-config.yml.example` |
| `524` ao preparar disco de backup | wizard passa dos 100 s da borda da Cloudflare | LAN, Tailscale ou `https://homelab.conradhub.com` sem depender de upload longo na borda |
| `conradhub.com` não resolve como em casa | sem Tailscale/split DNS ou Pi-hole parado | [Acesso remoto](SEGURANCA.md#acesso-remoto); em casa `dig @127.0.0.1 homelab.conradhub.com` → `192.168.0.150` |
| `pihole.conradhub.com` resolve fora de casa | registro DNS público indevido | remover do túnel e da zona pública; só Pi-hole local |
| Jellyfin abre mas play/stream dá 403 | fora da LAN `192.168.0.0/24` ou via Tailscale/túnel | esperado; stream só na LAN. Não publique Jellyfin em `0.0.0.0` |
| SMB não conecta fora | sem Tailscale ou Wi-Fi em `192.168.0.0/24` colidindo | `smb://homelab.conradhub.com/` com split DNS; se colidir, IP `100.x` do Pi ([REDE](REDE.md#nomes-publicos-e-lan)) |
| SMB não conecta pelo celular | `hosts allow` no `[global]` ou Pi-hole recusando `100.64.0.0/10` | ver [Acesso remoto](SEGURANCA.md#acesso-remoto) |

Logs:

```bash
sudo journalctl -u homelab-storage-agent -n 50
sudo tail -50 /var/log/homelab-storage-agent.log
docker compose logs -f web
sudo journalctl -u homelab-cloudflared -n 50
```
