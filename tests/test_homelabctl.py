from __future__ import annotations

import subprocess
import sys

from .conftest import ROOT

CLI = ROOT / "scripts" / "homelabctl.py"


def rodar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )


def test_list_mostra_os_dois_hosts():
    resultado = rodar("list")
    assert resultado.returncode == 0, resultado.stderr
    linhas = resultado.stdout.splitlines()
    assert any(linha.startswith("pi ") for linha in linhas)
    assert any(linha.startswith("moya ") for linha in linhas)


def test_check_valida_todos():
    resultado = rodar("check")
    assert resultado.returncode == 0, resultado.stderr
    assert "ok pi" in resultado.stdout
    assert "ok moya" in resultado.stdout
    assert "credenciais" in resultado.stdout  # feature listada no resumo


def test_check_falha_com_config_ruim(tmp_path, monkeypatch):
    # Um host quebrado no diretorio de hosts tem que derrubar o check.
    import shutil

    destino = tmp_path / "hosts"
    shutil.copytree(ROOT / "hosts", destino)
    (destino / "quebrado").mkdir()
    (destino / "quebrado" / "host.toml").write_text('[host]\nnome = "quebrado"\n')

    codigo = (
        "import sys; from pathlib import Path;"
        f"sys.path.insert(0, {str(ROOT)!r});"
        "import core.homelab_config as c;"
        f"c.DIR_HOSTS = Path({str(destino)!r});"
        f"sys.argv = ['homelabctl', 'check'];"
        "import runpy; runpy.run_path(" + repr(str(CLI)) + ", run_name='__main__')"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, cwd=ROOT
    )
    assert resultado.returncode == 2 or resultado.returncode == 1
    assert "quebrado" in resultado.stderr


def test_render_pi_imprime_o_host_env():
    resultado = rodar("render", "pi")
    assert resultado.returncode == 0, resultado.stderr
    assert 'SITE_NAME="Homelab Storage"' in resultado.stdout
    assert "HOST_PROFILE=pi" in resultado.stdout
    assert (
        "APPS_ENV_PATH=/opt/stacks/homelab-storage-admin/deploy/pi/apps.env"
        in resultado.stdout
    )
    assert "Gerado por homelabctl render" in resultado.stdout


def test_render_sync_do_moya():
    resultado = rodar("render", "moya", "--sync")
    assert resultado.returncode == 0, resultado.stderr
    assert "CADDY_PORTA=:80" in resultado.stdout
    assert "UPSTREAM_HOST=localhost" in resultado.stdout


def test_render_write_grava_e_faz_backup(tmp_path):
    primeira = rodar("render", "pi", "--write", "--ambos", "--destino", str(tmp_path))
    assert primeira.returncode == 0, primeira.stderr
    host_env = tmp_path / "host.env"
    assert host_env.is_file()
    assert (tmp_path / "sync.env").is_file()
    assert oct(host_env.stat().st_mode & 0o777) == "0o644"

    segunda = rodar("render", "pi", "--write", "--destino", str(tmp_path))
    assert segunda.returncode == 0, segunda.stderr
    assert "sem mudanca" in segunda.stdout
    # Sem mudanca nao cria backup a mais.
    assert not list(tmp_path.glob("host.env.bak-*"))


def test_render_host_inexistente_erra():
    resultado = rodar("render", "naoexiste")
    assert resultado.returncode == 2
    assert "naoexiste" in resultado.stderr
