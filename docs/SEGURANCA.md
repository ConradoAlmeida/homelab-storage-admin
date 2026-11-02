# Segurança e acesso remoto

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Instalação](INSTALACAO.md) · [Rede](REDE.md)

> Postura de segurança, Cloudflare Tunnel para o painel, Tailscale para SMB/DNS e checklist de verificação.

---

## Princípios de segurança

- Container escuta em `192.168.0.150:8060`, não em `0.0.0.0`.
- Acesso só na LAN. Para fora de casa, siga a [Acesso remoto](#acesso-remoto): Cloudflare Tunnel com
  Access para o painel e Tailscale para SMB/DNS. Nunca publique a porta 8060.
- O agente roda como root, mas só expõe operações da allowlist em
  `agent/homelab-storage-agent.py`.
- O socket é `0660 root:root`; o container roda como root para acessá-lo. Se
  quiser endurecer, crie um grupo dedicado e rode o container com esse grupo.
- O README antigo do projeto `moya-storage-admin` continha uma senha real. Ela
  **não** foi trazida para este repositório; rotacione a senha no servidor antigo
  se ele ainda existir.

---

## Acesso remoto

Fora de casa são duas necessidades diferentes, com duas ferramentas diferentes.
Não tente resolver as duas com o mesmo túnel.

| Necessidade | Ferramenta | Por quê |
|---|---|---|
| Painel e apps web (`:8060`, Jellyfin, Cockpit, Dockge) | Cloudflare Tunnel + Access | URL pública com HTTPS e MFA, sem abrir porta e sem cliente VPN |
| Arquivos (SMB) e nomes `.lan` | Tailscale (subnet router + split DNS) | SMB não trafega por HTTP; o Pi-hole precisa de rota até a LAN |

O `BIND_ADDR` continua `192.168.0.150`: o `cloudflared` roda no próprio Pi e
conecta em `http://192.168.0.150:8060` por dentro. Nenhum bind novo e nenhuma
porta publicada no roteador.

**No moyaserver** o perfil é outro: o bind é `127.0.0.1:8060` e quem publica é o
Caddy local. Se você montar túnel lá também, o `ingress` aponta para
`http://127.0.0.1:8060` (ou para o Caddy), nunca para o IP da LAN do Pi. Nada
neste documento muda o deploy do moya.

### Cloudflare Tunnel (painel e apps)

Pré-requisito: a zona do domínio precisa estar na Cloudflare (nameservers
apontados para ela). *Public hostname* não existe em domínio fora da zona.

1. Instale o `cloudflared` (`.deb` oficial) e **desabilite a unit do pacote**
   para não rodar dois conectores no mesmo túnel:

```
sudo systemctl disable --now cloudflared
```

2. Crie o túnel e a rota DNS:

```
cloudflared tunnel login
cloudflared tunnel create homelab
cloudflared tunnel route dns homelab storage.seudominio.com
```

3. Crie o usuário, a config e o credentials:

```
sudo useradd --system --home-dir /var/lib/cloudflared --create-home \
  --shell /usr/sbin/nologin cloudflared
sudo install -d -o root -g cloudflared -m 0750 /etc/cloudflared
sudo install -o root -g cloudflared -m 0640 ~/.cloudflared/<UUID>.json /etc/cloudflared/
sudo install -o root -g cloudflared -m 0640 \
  deploy/pi/cloudflared-config.yml.example /etc/cloudflared/config.yml
sudoedit /etc/cloudflared/config.yml   # UUID, credentials-file e hostname
```

4. Suba a unit:

```
sudo install -m 0644 deploy/pi/homelab-cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-cloudflared
```

5. **Access é obrigatório.** No Zero Trust → Access → Applications → Add
   self-hosted, aponte para `storage.seudominio.com` com policy `Allow` para o
   seu e-mail (One-time PIN) ou IdP. Sem isso o login do Django é a única
   barreira, e o app controla um agente root.

6. Acrescente o hostname ao `.env` e redeploy:

```
DJANGO_ALLOWED_HOSTS=...,storage.seudominio.com
DJANGO_CSRF_TRUSTED_ORIGINS=...,https://storage.seudominio.com
DJANGO_SECURE_COOKIES=1
```

O `SECURE_PROXY_SSL_HEADER` já está em `config/settings.py`, então o Django
reconhece o HTTPS terminado na Cloudflare. `BIND_ADDR` e overlay não mudam.

#### Cookies e HTTPS na LAN

`DJANGO_SECURE_COOKIES=1` marca o cookie como `Secure`: o navegador **para de
enviá-lo em `http://192.168.0.150:8060`** e o login pela LAN falha. Escolha uma:

| Opção | Efeito |
|---|---|
| Caddy do Pi na frente, com TLS interno (`https://storage.homelab.lan`) | LAN e WAN em HTTPS; instale o CA raiz do Caddy nos clientes |
| `DJANGO_SECURE_COOKIES=0` | LAN em HTTP volta a funcionar; o cookie só é cifrado na Cloudflare, não na LAN |
| Manter `1` e usar a LAN por IP só como emergência | simples, mas quebra o hábito de usar a LAN |

#### Limites da Cloudflare que afetam este app

- **Timeout de 100 s na borda** (free/Pro): o wizard **Backups → disco**
  (`timeout 900 s` no Gunicorn) estoura com **524** quando disparado pelo túnel.
  Rode esse passo pela LAN ou pelo Tailscale.
- **ToS 2.8:** o plano free não serve vídeo/arquivos grandes de forma
  desproporcional a HTML. **Jellyfin não deve ir por aqui.** Painel, `/history/`
  leve e downloads ocasionais, tudo bem.
- **100 MB por request** (free/Pro): upload por formulário acima disso falha.
- **Cloudflare fora do ar** deixa o painel inacessível. Mantenha o acesso por IP
  na LAN como fallback documentado.

### Tailscale (arquivos e DNS)

SMB continua sem passar por HTTP. Instale o Tailscale no Pi e use-o como **subnet
router**: os dispositivos passam a enxergar a `192.168.0.0/24` inteira, então
`BIND_ADDR`, `smb.conf` e `ALLOWED_HOSTS` não mudam.

```
echo 'net.ipv4.ip_forward = 1'          | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale up --advertise-routes=192.168.0.0/24
```

Aprove a rota no admin console (**Machines → homelab → Edit route settings**).

DNS: **não** use o Pi-hole como resolver global ("Override local DNS") — se o Pi
cair, o celular fica sem internet. Use **split DNS**:

- Admin console → DNS → Nameservers → Add → Custom → `100.x.y.z` (IP Tailscale do Pi)
- **Restrict to domain** → `homelab.lan`

Assim só `*.homelab.lan` vai para o Pi-hole; o resto continua no DNS da rede onde
você estiver. O Pi-hole precisa aceitar query de fora das subnets locais:

- Pi-hole v6: **Settings → DNS**, responder em todas as origens.
- `ufw`: liberar `53` **na interface `tailscale0`**:

```
sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto udp
sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto tcp
```

Atenção ao conflito de faixa: `192.168.0.0/24` é o default de quase todo roteador
doméstico. Num Wi-Fi de terceiro que use a mesma faixa, a rota colide e o acesso
"desaparece". Nesse caso use o IP Tailscale do Pi (`100.x.y.z`) diretamente —
funciona sempre.

Desative a expiração de chave do nó do Pi no console; senão ele sai do tailnet
em ~180 dias e você perde o acesso remoto.

### Checklist de verificação

```
# tunnel no ar e rota criada
sudo systemctl status homelab-cloudflared
cloudflared tunnel info homelab

# app respondendo local (deve dar 302/200)
curl -fsS -o /dev/null -w '%{http_code}\n' http://192.168.0.150:8060/login/

# de fora: deve redirecionar para o login do Access, não direto para o Django
curl -sI https://storage.seudominio.com/login/ | head -5

# VPN e DNS
tailscale status
tailscale ping <celular>              # precisa dizer "direct", não "via DERP"
dig +short storage.homelab.lan @100.x.y.z
testparm -s | grep -iE 'interfaces|hosts allow'   # vazio = liberado para todos
```

No Windows 11, depois do Tailscale: `\\192.168.0.150\documentos`. No celular, iOS
em **Arquivos → Conectar ao servidor → `smb://192.168.0.150`**; Android com
qualquer cliente SMB.

Nunca: publicar `8060` no roteador, expor `445` na internet, usar *trycloudflare*
como endereço permanente ou apontar o Jellyfin para o túnel gratuito.
