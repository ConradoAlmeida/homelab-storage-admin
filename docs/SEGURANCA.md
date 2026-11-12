# Segurança e acesso remoto

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Instalação](INSTALACAO.md) · [Rede](REDE.md)

> Postura de segurança, Tailscale fora de casa, cookies HTTPS e checklist.

---

## Princípios de segurança

- Container escuta em `192.168.0.150:8060` (não em `0.0.0.0`), atrás do Caddy.
  Não publique `8060` no roteador. Fora de casa só o Tailscale
  ([Acesso remoto](#acesso-remoto)).
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

Fora de casa só o Tailscale. Não há `cloudflared`, túnel nem aplicação Access
na frente dos apps. A conta tem Zero Trust Free e One-time PIN; isso não entra
no caminho. Nomes, rota, split DNS e portas do UFW:
[REDE](REDE.md#nomes).

A zona `conradhub.com` na Cloudflare serve o nome e o certificado Let's
Encrypt (DNS-01). Os cinco nomes não têm A nem CNAME público. O token de API
(Zone DNS Edit, só a zona) fica em `/opt/stacks/caddy/cloudflare.token`, modo
600, root, fora do Git. Ele só cria o TXT do desafio.

O `BIND_ADDR` do container continua `192.168.0.150:8060`. O Caddy do Pi
(`homelab-caddy:2`, stack `/opt/stacks/caddy`, network host) termina o TLS.
**No moyaserver** o bind é `127.0.0.1:8060` e o Caddy local publica. ZeroTier
e o perfil do moya não mudam.

Gestão (Samba, shares, snapshots, firewall, start/stop/restart/logs) continua
sendo HTTP para o Django; o agente local executa. Confirmações destrutivas
permanecem.

### Cookies e HTTPS

`DJANGO_SECURE_COOKIES=1` quando o mesmo `https://homelab.conradhub.com` vale
em casa e no Tailscale. No Pi isso já vale: a flag está no `.env` e no
container desde o `./deploy.sh` de 2026-11-04. O login nesse nome grava cookie
`Secure`. `http://192.168.0.150:8060` abre a página e não mantém sessão.

O exemplo do repositório continua `0`, para instalação nova. O
`SECURE_PROXY_SSL_HEADER` em `config/settings.py` faz o Django enxergar HTTPS
vindo do Caddy.

### Jellyfin

- A UI abre pelo Tailscale e na LAN.
- Play, stream e download com origem `100.64.0.0/10` ou cabeçalho
  `CF-Connecting-IP` recebem 403 ("Playback fora da LAN"). Na LAN o vídeo toca.
  Prova de 2026-11-04: no 5G o playback falhou; na LAN reproduziu.
- Não publique a porta do Jellyfin no roteador. Não mande vídeo nem SMB pela
  Cloudflare.

### Tailscale

Substitui o ZeroTier só no Pi. Estado no ar: nó `homelab`, `100.84.34.25`,
MagicDNS `homelab.tail1a4ccb.ts.net`, SSH desligado, chave sem expiração, rota
`192.168.0.0/24` aprovada. Split DNS de `conradhub.com` → `100.84.34.25`,
restrito a esse sufixo, sem override global.

Referência de como o nó foi anunciado:

```
echo 'net.ipv4.ip_forward = 1'          | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale up --advertise-routes=192.168.0.0/24
```

A rota se aprova no admin console. O UFW no Pi aceita `100.64.0.0/10` em DNS,
80, 443, 8060, 9090, 5001, 8096 e nas portas Samba 445/139/137/138. O Samba
escuta em `0.0.0.0:445`.

Wi-Fi de terceiro em `192.168.0.0/24` colide com a rota. Use
`smb://homelab.conradhub.com/` ou o IP `100.x` do Pi.

### Admins locais dos apps Django

No moyaserver, `Sistema → Admins locais` permite criar o superuser local
`admin` e rotacionar a senha dele nos apps Django (Credenciais, Storage,
Datasheets, Drawing e Process Manager). A página só abre para um superuser do
Storage Admin.

- A interface manda só o slug do app. O agente usa uma registry fixa de
  containers e executa apenas `manage.py shell` com um trecho constante; não
  aceita container, caminho ou comando do cliente.
- A senha é gerada no agente, enviada ao container por **stdin** e devolvida
  uma única vez na resposta. Não vai para argv, `host.env`, banco do Storage,
  log do agente ou `AuditLog`.
- A rotação exige digitar o identificador do app e invalida a senha anterior.
- Criar preserva a senha apenas quando `admin` já é superuser com senha
  utilizável; se faltar, não for superuser ou estiver sem senha, gera uma nova.
- Superusers com outro nome (por exemplo `conrado`) não são alterados.
- `DJANGO_ADMIN_MANAGE=0` no host desliga a página e as ações, mesmo que o
  agente ofereça a operação. `DJANGO_ADMIN_ENABLE=0` desliga no agente.
- O caminho normal continua sendo o Credenciais/SSO; este admin é break-glass.

### Checklist de verificação

```
curl -fsS -o /dev/null -w '%{http_code}\n' https://homelab.conradhub.com/login/
dig +short homelab.conradhub.com @192.168.0.150    # em casa: 192.168.0.150
dig +short homelab.conradhub.com @1.1.1.1          # vazio
dig +short pihole.conradhub.com @1.1.1.1           # vazio
tailscale status
testparm -s | grep -iE 'interfaces|hosts allow'
```

Nunca: publicar porta no roteador, expor `445` na internet, ou mandar vídeo
ou SMB pela Cloudflare.
