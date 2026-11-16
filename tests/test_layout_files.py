from __future__ import annotations

from pathlib import Path

from .conftest import ROOT, parse_env_file


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_compose_has_no_pi_ip():
    text = read("docker-compose.yml")
    assert "192.168.0.150" not in text
    assert "BIND_ADDR" in text
    assert "AGENT_SOCKET" in text
    assert "TERMINAL_SOCKET=${TERMINAL_SOCKET:-/run/homelab-storage-admin/terminal.sock}" in text
    assert "TERMINAL_SOCKET=${TERMINAL_SOCKET:-}" not in text
    assert "TORRENT_API_TOKEN=${TORRENT_API_TOKEN:-}" in text


def test_homelab_overlay_keeps_current_paths():
    text = read("docker-compose.homelab.yml")
    assert "/mnt/nas/apps/homelab-storage-admin/data:/app/data" in text
    assert "/mnt/nas:/mnt/nas:ro" in text
    assert "${JELLYFIN_ROOT:-/mnt/jellyfin}:${JELLYFIN_ROOT:-/mnt/jellyfin}:ro" in text
    assert "/run/homelab-storage-admin:/run/homelab-storage-admin:ro" in text
    assert "container_name: qbittorrent" in text
    assert "network_mode: host" in text
    assert 'WEBUI_PORT: "8090"' in text
    assert 'TORRENTING_PORT: "6881"' in text
    assert "QBITTORRENT_URL: http://qbittorrent:8090" in text
    assert "qbittorrent:host-gateway" in text
    assert "6881:6881" not in text
    assert "8080:8080" not in text


def test_host_env_example_is_pi_profile():
    values = parse_env_file(ROOT / "host.env.example")
    assert values["STORAGE_ROOT"] == "/mnt/nas"
    assert values["ALLOWED_PATH_PREFIXES"] == "/mnt/nas/"
    assert values["BIND_ADDR"] == "192.168.0.150"
    assert values["SNAPSHOT_BACKEND"] == "auto"
    assert values["COMPOSE_OVERLAY"] == "docker-compose.homelab.yml"
    assert values["TORRENT_API_TOKEN"] == ""
    assert values["SYSTEM_MANAGE"] == "1"
    assert values["TERMINAL_ENABLE"] == "1"


def test_metrics_timer_is_installed_and_daily():
    timer = read("agent/homelab-storage-metrics.timer")
    service = read("agent/homelab-storage-metrics.service")
    install = read("install-agent.sh")
    assert "OnCalendar=*-*-* 06:00:00" in timer
    assert "--collect" in service
    assert "homelab-storage-metrics.timer" in install


def test_install_agent_checks_deps_from_features():
    # A dependencia segue a feature ligada no host.toml; o hardcoded de Samba e
    # so o fallback de host sem TOML.
    text = read("install-agent.sh")
    assert 'homelabctl.py" requisitos' in text
    assert "feature ligada em hosts/$HOST_ENV_PROFILE/host.toml" in text
    assert "obrig" in text and "opc" in text
    assert "host.env" in text
    assert '[[ -f "$CONFIG_DIR/$arquivo" ]]' in text
    assert "python3 \"$HERE/scripts/homelabctl.py\" render" in text


def test_unit_uses_host_env_and_preserves_socket_name():
    text = read("agent/homelab-storage-agent.service")
    assert "EnvironmentFile=-/etc/homelab-storage-admin/host.env" in text
    assert "RuntimeDirectory=homelab-storage-admin" in text
    assert "Environment=STORAGE_ROOT" not in text


def test_pi_boot_unit_uses_host_env_and_overlay():
    text = read("deploy/pi/homelab-compose.service")
    assert "/etc/homelab-storage-admin/host.env" in text
    assert "COMPOSE_OVERLAY" in text
    assert "homelab-storage-admin" in text
    assert "ip -4 addr show | grep" in text
    assert "show dev wlan0" not in text


def test_jellyfin_boot_unit_waits_for_media_mount():
    text = read("deploy/pi/jellyfin-compose.service")
    assert "Requires=docker.service mnt-jellyfin.mount mnt-nas.mount" in text
    assert "BindsTo=mnt-jellyfin.mount" in text
    assert "After=docker.service mnt-jellyfin.mount mnt-nas.mount" in text
    assert "WorkingDirectory=/opt/stacks/jellyfin" in text
    assert "findmnt --mountpoint /mnt/jellyfin" in text
    assert "unless-stopped" not in text


def test_pi_motd_points_to_storage_admin():
    text = read("deploy/pi/motd")
    assert "Storage admin:" in text
    assert "https://homelab.conradhub.com/" in text


def test_deploy_loads_host_env_and_selected_overlay():
    text = read("deploy.sh")
    assert "/etc/homelab-storage-admin/host.env" in text
    assert "COMPOSE_OVERLAY" in text
    assert "docker-compose.homelab.yml" not in text
    assert 'docker compose "${COMPOSE_FILES[@]}" up -d --build' in text
    assert "docker exec -i homelab-storage-admin python -" in text
    assert 'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")' in text
    assert "django.setup()" in text
    assert "6881/tcp" in text
    assert "6881/udp" in text
    assert "8090/tcp" in text
    assert "172.16.0.0/12" in text
    assert '"upnp": True' in text


def test_deploy_confere_app_viva():
    text = read("deploy.sh")
    # Deploy verde = /login/ respondendo no endereco em que o host publica.
    assert 'APP_URL="http://${BIND_ADDR:-127.0.0.1}:${BIND_PORT:-8060}/login/"' in text
    assert "OK: $APP_URL -> $APP_CODE" in text
    assert "logs --tail=80 web" in text
    # O doctor entra no fim do deploy e so informa (nao muda o exit code).
    assert "==> rotas, DNS e atalhos (--doctor)" in text
    assert "apps-sync.sh$APPS_PERFIL --doctor" in text
    assert "set +e" in text and "DOUTOR_RC=$?" in text
    assert "exit 1" not in text.split("==> rotas, DNS e atalhos")[1]


def test_deploy_relanca_quando_o_pull_muda_o_proprio_script():
    text = read("deploy.sh")
    # Bash le por offset: sem re-exec o deploy que atualiza a si mesmo roda o
    # tail antigo (ou lixo) no lugar das linhas novas.
    assert 'DEPLOY_ANTES="$(cksum <"$0")"' in text
    assert 'DEPLOY_REEXECUTADO=1 exec "$0" "$@"' in text


def test_deploy_cobra_o_apply_do_env():
    text = read("deploy.sh")
    # env mais novo que o estado do --apply vira aviso com o comando do perfil.
    assert "apps.aplicados" in text
    assert '"$APPS_ENV_LOCAL" -nt "$APPS_ESTADO"' in text
    assert "sudo bash scripts/stacks/apps-sync.sh$APPS_PERFIL --apply" in text
    assert "moya) APPS_PERFIL=\" --perfil moya\"" in text
    # O deploy nao aplica sozinho: precisa de sudo e a decisao e do dono.
    assert not [
        linha
        for linha in text.splitlines()
        if linha.strip().startswith(("bash scripts/stacks", "sudo bash scripts/stacks"))
    ]


def test_ci_guarda_css_compilado_e_migracoes():
    text = read(".github/workflows/ci.yml")
    assert "makemigrations --check --dry-run" in text
    assert "manage.py tailwind build" in text
    assert "git diff --exit-code -- static/css/kit.css" in text


def test_install_agent_selects_profile():
    text = read("install-agent.sh")
    assert "HOST_ENV_PROFILE" in text
    # Qualquer slug de hosts/ vale; os exemplos sao so o fallback antigo.
    assert 'hosts/$HOST_ENV_PROFILE/host.toml' in text
    assert "host.env.moya.example" in text
    assert "host.env.example" in text


def test_templates_have_no_inline_css_or_js():
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "<style" not in text, path
        assert "<script>" not in text, path
        assert 'style="' not in text, path
        assert "onclick=" not in text, path
        assert "onsubmit=" not in text, path


def test_css_links_use_automatic_static_version():
    for name in ("base.html", "base_auth.html"):
        text = (ROOT / "templates" / name).read_text(encoding="utf-8")
        assert text.count("?v={{ static_version }}") == 3, name


def test_static_assets_exist():
    assert (ROOT / "static" / "css" / "app.css").is_file()
    assert (ROOT / "frontend" / "src.css").is_file()
    kit = ROOT / "static" / "css" / "kit.css"
    assert kit.is_file()
    texto = kit.read_text(encoding="utf-8")
    assert ".person-id{" in texto
    assert ".group-strip{" in texto
    assert ".torrent-page" in texto
    assert "tailwindcss/preflight" not in texto
    for name in (
        "confirm-actions.js",
        "copy-secret.js",
        "django-admins.js",
        "service-tint.js",
        "table-filter.js",
        "table-sort.js",
        "auto-refresh.js",
        "gitea-status.js",
        "disk-wizard.js",
        "job-form.js",
        "live-metrics.js",
        "network-metrics.js",
        "share-sizes.js",
    ):
        assert (ROOT / "static" / "js" / name).is_file(), name
