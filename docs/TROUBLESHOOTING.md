# Troubleshooting

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Segurança](SEGURANCA.md) · [Instalação](INSTALACAO.md)

> Sintomas, causas e correções dos problemas mais comuns.

---

| Sintoma | Causa provável | Ação |
|---|---|---|
| “Agente indisponível” | serviço parado ou socket ausente | `sudo systemctl status homelab-storage-agent` |
| `ModuleNotFoundError: No module named 'django'` | rodou `python3 manage.py` no host, fora do venv/container | use `uv run manage.py ...` ou `docker compose exec web ...` |
| `attempt to write a readonly database` | rodou no diretório antigo `~/homelab-storage-admin` ou sem `DJANGO_SQLITE_PATH` | use `/opt/stacks/homelab-storage-admin` e o banco em `/mnt/nas/apps/...`; ou o container |
| `btrfs ... not a subvolume` | pasta ainda é diretório comum | ativar a política e confirmar o nome do share para converter |
| `/mnt/nas nao esta montado` | array não montado | `mount /mnt/nas` / conferir `fstab` |
| `testparm` falhou | seção inválida no `smb.conf` | o app restaura o backup; revisar o log |
| Versões anteriores vazias | `shadow_copy2`/`shadow:snapdir` errado | conferir a seção do share e reiniciar o `smbd` |
| `400 Bad Request` em `homelab.conradhub.com` | hostname fora de `DJANGO_ALLOWED_HOSTS` | acrescentar `homelab.conradhub.com` e rodar `./deploy.sh` |
| `CSRF verification failed` em `https://homelab.conradhub.com` | origem fora de `DJANGO_CSRF_TRUSTED_ORIGINS` | acrescentar `https://homelab.conradhub.com` |
| `http://192.168.0.150:8060` abre e não mantém sessão | `DJANGO_SECURE_COOKIES=1`; o cookie é `Secure` | usar `https://homelab.conradhub.com`. No Pi a flag já está ligada. O exemplo do repo fica em `0` até esse nome valer em casa e no Tailscale ([Cookies e HTTPS](SEGURANCA.md#cookies-e-https)) |
| Troca de senha sem alerta de sucesso/fracasso | POST inválido (campo hidden) ou só o aviso do Chrome em HTTP | a tela mostra `alert`; o log do agente tem `SET_PASSWORD` se gravou. O aviso “Password fields present on an insecure (http://) page” é o Chrome, não o app |
| Nome `.com` não resolve fora de casa | sem Tailscale, split DNS ausente ou Pi-hole parado | [Nomes](REDE.md#nomes). Em casa `dig @192.168.0.150 homelab.conradhub.com` → `192.168.0.150`. `dig @1.1.1.1` volta vazio |
| `pihole.conradhub.com` resolve em `1.1.1.1` | A ou CNAME público na zona | apagar o registro. O nome só existe no Pi-hole, em casa ou com Tailscale |
| Jellyfin abre mas play/stream dá 403 | origem `100.64.0.0/10` ou cabeçalho `CF-Connecting-IP` | esperado ("Playback fora da LAN"). Na LAN o vídeo toca. Não publique a porta no roteador |
| SMB não conecta fora | sem Tailscale ou Wi-Fi em `192.168.0.0/24` colidindo | `smb://homelab.conradhub.com/` com split DNS; se colidir, IP `100.x` do Pi ([REDE](REDE.md#nomes)) |
| SMB não conecta pelo celular | `hosts allow` no `[global]`, UFW ou Pi-hole recusando `100.64.0.0/10` | ver [Acesso remoto](SEGURANCA.md#acesso-remoto) |

Logs:

```bash
sudo journalctl -u homelab-storage-agent -n 50
sudo tail -50 /var/log/homelab-storage-agent.log
docker compose logs -f web
```
