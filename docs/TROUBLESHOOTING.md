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
| `400 Bad Request` no domínio público | hostname fora de `DJANGO_ALLOWED_HOSTS` | acrescentar e rodar `./deploy.sh` |
| `CSRF verification failed` atrás do túnel | origem `https://` fora de `DJANGO_CSRF_TRUSTED_ORIGINS` | acrescentar `https://storage.seudominio.com` |
| Login ok fora de casa, falha na LAN | `DJANGO_SECURE_COOKIES=1` com acesso HTTP | ver [Acesso remoto](SEGURANCA.md#acesso-remoto), "Cookies e HTTPS na LAN" |
| `502` no `cloudflared` | `config.yml` aponta para `127.0.0.1` ou porta errada | `curl -I http://192.168.0.150:8060/login/` no Pi |
| `524` ao preparar disco de backup | wizard passa dos 100 s da borda da Cloudflare | rodar pela LAN ou pelo Tailscale ([Acesso remoto](SEGURANCA.md#acesso-remoto)) |
| `.lan` não resolve fora de casa | sem split DNS/Tailscale | ver [Acesso remoto](SEGURANCA.md#acesso-remoto) |
| SMB não conecta pelo celular | `hosts allow` no `[global]` ou Pi-hole recusando `100.64.0.0/10` | ver [Acesso remoto](SEGURANCA.md#acesso-remoto) |

Logs:

```bash
sudo journalctl -u homelab-storage-agent -n 50
sudo tail -50 /var/log/homelab-storage-agent.log
docker compose logs -f web
sudo journalctl -u homelab-cloudflared -n 50
```
