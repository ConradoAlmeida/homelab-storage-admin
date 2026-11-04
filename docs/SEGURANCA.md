# Segurança e acesso remoto

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Instalação](INSTALACAO.md) · [Rede](REDE.md)

> Postura de segurança, Cloudflare Tunnel para o painel, Tailscale para SMB/DNS e checklist de verificação.

---

## Princípios de segurança

- Container escuta em `192.168.0.150:8060` (não em `0.0.0.0`), atrás do Caddy;
  não publique `8060` no roteador. Fora de casa: [Acesso remoto](#acesso-remoto)
  (túnel + Access nos quatro nomes públicos; Tailscale para SMB e DNS).
- O agente roda como root, mas só expõe operações da allowlist em
  `agent/homelab-storage-agent.py`.
- O socket é `0660 root:root`; o container roda como root para acessá-lo. Se
  quiser endurecer, crie um grupo dedicado e rode o container com esse grupo.
- O README antigo do projeto `moya-storage-admin` continha uma senha real. Ela
  **não** foi trazida para este repositório; rotacione a senha no servidor antigo
  se ele ainda existir.
- Senha Samba não fica em texto em lugar nenhum. O Samba guarda só o hash NT,
  sem salt, em `/var/lib/samba/private/passdb.tdb` (diretório `0700 root`). Quem
  tem root no host extrai o hash e quebra offline; unificar a senha com o
  Credenciais não muda isso. O app não copia esse arquivo em backup.

---

## Acesso remoto

Fora de casa entram duas ferramentas: **Cloudflare Tunnel + Access** nos quatro
hostnames públicos (`homelab`, `cockpit`, `dockge`, `jellyfin.conradhub.com`) e
**Tailscale** no Pi para SMB e para resolver `conradhub.com` como em casa.
`pihole.conradhub.com` não tem DNS público.

O `BIND_ADDR` do container continua `192.168.0.150:8060`. O Caddy na frente
termina TLS (Let's Encrypt, DNS-01; token só no Pi, fora do Git). O
`cloudflared` roda **só no Pi** e encaminha cada hostname público para
`https://192.168.0.150` com o mesmo nome; demais hostnames → 404. Nenhum
`cloudflared` no notebook ou celular. Credencial do túnel e token DNS-01 ficam
no Pi, nunca no Git.

**No moyaserver** o bind é `127.0.0.1:8060` e o Caddy local publica; este
roteiro é do Pi. ZeroTier e perfil do moya não mudam.

Gestão (Samba, shares, snapshots, firewall, start/stop/restart/logs) continua
sendo HTTP para o Django; o agente local executa. Confirmações destrutivas
permanecem.

### Cloudflare Tunnel e Access

Pré-requisito: zona `conradhub.com` na Cloudflare.

1. Instale o `cloudflared` (`.deb` oficial) e **desabilite a unit do pacote**
   para não rodar dois conectores no mesmo túnel:

```
sudo systemctl disable --now cloudflared
```

2. Crie o túnel e as rotas DNS dos quatro hostnames (sem `pihole`):

```
cloudflared tunnel login
cloudflared tunnel create homelab
cloudflared tunnel route dns homelab homelab.conradhub.com
cloudflared tunnel route dns homelab cockpit.conradhub.com
cloudflared tunnel route dns homelab dockge.conradhub.com
cloudflared tunnel route dns homelab jellyfin.conradhub.com
```

3. Usuário, credentials e config (UUID e JSON só no host):

```
sudo useradd --system --home-dir /var/lib/cloudflared --create-home \
  --shell /usr/sbin/nologin cloudflared
sudo install -d -o root -g cloudflared -m 0750 /etc/cloudflared
sudo install -o root -g cloudflared -m 0640 ~/.cloudflared/TROQUE-PELO-UUID.json /etc/cloudflared/
sudo install -o root -g cloudflared -m 0640 \
  deploy/pi/cloudflared-config.yml.example /etc/cloudflared/config.yml
sudoedit /etc/cloudflared/config.yml
```

4. Unit `homelab-cloudflared`:

```
sudo install -m 0644 deploy/pi/homelab-cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-cloudflared
```

5. **Access** nos quatro hostnames: policy `Allow` com One-time PIN no e-mail
   do dono (placeholder no doc; use o real só no console Cloudflare).

6. No `.env` do Pi, junto com o deploy de rede, acrescente o hostname público
   do painel e ligue cookies seguros **só quando casa e túnel usarem o mesmo
   `https://homelab.conradhub.com`** (ver `.env.example`).

O `SECURE_PROXY_SSL_HEADER` em `config/settings.py` faz o Django enxergar HTTPS
vindo do Caddy/Cloudflare.

#### Cookies e HTTPS

`DJANGO_SECURE_COOKIES=1` exige que o login em casa também seja HTTPS no mesmo
nome (`https://homelab.conradhub.com`), não `http://192.168.0.150:8060`. Até o
Caddy e o `.env` do Pi estarem alinhados, deixe `0` no clone (`.env.example`).

#### Jellyfin e limites da Cloudflare

- A **UI** do Jellyfin abre pelo Tailscale e pelo túnel (com Access fora de casa).
- **Play, stream e download** fora da LAN `192.168.0.0/24` respondem **403**
  (bloqueio de origem `100.64.0.0/10` e de pedidos com `CF-Connecting-IP` no
  Caddy). Não publique a porta do container Jellyfin em `0.0.0.0`.
- Plano free: **ToS 2.8** — não use a borda para vídeo; stream real só na LAN.
- **100 s / 524** e **100 MB** por request: igual ao painel ([TROUBLESHOOTING](TROUBLESHOOTING.md)).

### Tailscale (SMB e DNS)

Substitui o ZeroTier **só no Pi**. Subnet router `192.168.0.0/24`:

```
echo 'net.ipv4.ip_forward = 1'          | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale up --advertise-routes=192.168.0.0/24
```

Aprove a rota no admin console. **Sem** Tailscale SSH. Desative expiração da
chave do nó do Pi.

Split DNS (**sem** override global): domínio `conradhub.com` → IP Tailscale do
Pi (Pi-hole). UFW: liberar `53` em `tailscale0` para `100.64.0.0/10`. Pi-hole
aceita query de fora das subnets locais.

Wi-Fi de terceiro em `192.168.0.0/24` colide com a rota anunciada; use
`smb://homelab.conradhub.com/` resolvendo pelo Pi-hole ou o IP `100.x` do Pi.

Com Tailscale, os mesmos `https://` de casa **sem** PIN do Access. Casos A–D:
[REDE](REDE.md#nomes-publicos-e-lan).

### Checklist de verificação

```
sudo systemctl status homelab-cloudflared
cloudflared tunnel info homelab
curl -fsS -o /dev/null -w '%{http_code}\n' https://192.168.0.150/login/ -H 'Host: homelab.conradhub.com' --insecure
curl -sI https://homelab.conradhub.com/login/ | head -5    # fora: Access antes do Django
dig +short homelab.conradhub.com @127.0.0.1                  # em casa: 192.168.0.150
dig +short pihole.conradhub.com @1.1.1.1                     # fora: NXDOMAIN ou sem registro público
tailscale status
testparm -s | grep -iE 'interfaces|hosts allow'
```

Nunca: publicar `8060` ou Jellyfin em `0.0.0.0`, expor `445` na internet,
*trycloudflare* permanente, ou confiar na borda free para stream de vídeo.
