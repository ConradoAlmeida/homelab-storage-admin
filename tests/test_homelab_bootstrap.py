from __future__ import annotations

from pathlib import Path

import pytest

from core.homelab_bootstrap import preparar
from core.homelab_config import ConfigError, carregar_arquivo, texto_host_env

TOML = """\
[host]
nome = "mini"
ssh = "conrado@mini"
lan_ip = "10.0.0.2"
repo = "{repo}"

[app]
site_name = "Mini"
bind_addr = "10.0.0.2"
bind_port = 8061

[caminhos]
dados = "{tmp}/dados"
backup = "{tmp}/backup"
config = "{tmp}/etc"

[armazenamento]
proprietario = "conrado"
mounts = []

[rotas]
apps = "deploy/mini/apps.env"
esquema = "https"

[features]
samba = true
"""

EXEMPLO = """\
# exemplo
DJANGO_SECRET_KEY=troque-por-uma-chave-aleatoria-longa
DJANGO_ALLOWED_HOSTS=192.168.0.150,homelab,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://192.168.0.150:8060,http://homelab:8060
DJANGO_DEBUG=0
"""


def faz_host(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "deploy" / "mini").mkdir(parents=True)
    (repo / "deploy" / "mini" / "apps.env").write_text("", encoding="utf-8")
    (repo / ".env.example").write_text(EXEMPLO, encoding="utf-8")
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(
        TOML.replace("{tmp}", str(tmp_path)).replace("{repo}", str(repo)),
        encoding="utf-8",
    )
    return carregar_arquivo(arquivo), repo


def test_sem_escrever_nao_toca_em_nada(tmp_path):
    cfg, repo = faz_host(tmp_path)
    linhas = preparar(
        cfg,
        repo=repo,
        config_dir=tmp_path / "etc",
        which=lambda _n: "/usr/bin/x",
    )
    assert not (tmp_path / "etc").exists()
    assert not (repo / ".env").exists()
    # O dry-run diz o comando em vez de executar.
    assert any("(sim) geraria" in linha for linha in linhas)
    assert any("./deploy.sh" in linha for linha in linhas)


def test_escrever_gera_env_e_env_com_segredo(tmp_path):
    cfg, repo = faz_host(tmp_path)
    config = tmp_path / "etc"
    linhas = preparar(
        cfg, escrever=True, repo=repo, config_dir=config,
        which=lambda _n: "/usr/bin/x",
    )
    assert (config / "host.env").read_text(encoding="utf-8") == texto_host_env(cfg)
    assert "DNS_MODE=nenhum" in (config / "sync.env").read_text(encoding="utf-8")
    assert any("escrito" in linha for linha in linhas)

    env = repo / ".env"
    texto = env.read_text(encoding="utf-8")
    assert env.stat().st_mode & 0o777 == 0o600
    assert "troque-por-uma-chave" not in texto
    segredo = [l for l in texto.splitlines() if l.startswith("DJANGO_SECRET_KEY=")]
    assert len(segredo[0]) == len("DJANGO_SECRET_KEY=") + 64
    assert "DJANGO_ALLOWED_HOSTS=10.0.0.2,mini,localhost,127.0.0.1" in texto
    assert "https://10.0.0.2:8061" in texto


def test_env_existente_nunca_e_sobrescrito(tmp_path):
    cfg, repo = faz_host(tmp_path)
    env = repo / ".env"
    env.write_text("DJANGO_SECRET_KEY=" + "b" * 64 + "\n", encoding="utf-8")
    env.chmod(0o644)
    preparar(
        cfg, escrever=True, repo=repo, config_dir=tmp_path / "etc",
        which=lambda _n: "/usr/bin/x",
    )
    assert env.read_text(encoding="utf-8") == "DJANGO_SECRET_KEY=" + "b" * 64 + "\n"
    assert env.stat().st_mode & 0o777 == 0o644  # avisa, nao conserta escondido


def test_host_env_existente_fica_para_o_render(tmp_path):
    cfg, repo = faz_host(tmp_path)
    config = tmp_path / "etc"
    config.mkdir()
    (config / "host.env").write_text("SITE_NAME=\"Velho\"\n", encoding="utf-8")
    linhas = preparar(
        cfg, escrever=True, repo=repo, config_dir=config,
        which=lambda _n: "/usr/bin/x",
    )
    assert (config / "host.env").read_text(encoding="utf-8") == "SITE_NAME=\"Velho\"\n"
    assert any("render --write" in linha for linha in linhas)


def test_apt_so_com_escrever_e_root(tmp_path):
    cfg, repo = faz_host(tmp_path)
    rodados: list[list[str]] = []
    linhas = preparar(
        cfg, apt=True, repo=repo, config_dir=tmp_path / "etc",
        which=lambda _n: None, executar=rodados.append, geteuid=lambda: 0,
    )
    assert rodados and rodados[0][0] == "apt-get"
    assert "samba" in rodados[0]
    assert any(linha.startswith("apt install ") for linha in linhas)

    with pytest.raises(ConfigError) as exc:
        preparar(
            cfg, apt=True, repo=repo, config_dir=tmp_path / "outro",
            which=lambda _n: None, executar=rodados.append,
            geteuid=lambda: 1000,
        )
    assert "exige root" in str(exc.value)
    assert len(rodados) == 1  # nao tentou instalar sem root


def test_sem_apt_e_so_lista_o_comando(tmp_path):
    cfg, repo = faz_host(tmp_path)
    rodados: list[list[str]] = []
    linhas = preparar(
        cfg, repo=repo, config_dir=tmp_path / "etc",
        which=lambda _n: None, executar=rodados.append, geteuid=lambda: 0,
    )
    assert rodados == []
    assert any("faltam dependencias: apt install" in linha for linha in linhas)


def test_dependencia_presente_nao_pede_apt(tmp_path):
    cfg, repo = faz_host(tmp_path)
    linhas = preparar(
        cfg, repo=repo, config_dir=tmp_path / "etc", which=lambda _n: "/usr/bin/x"
    )
    assert "dependencias obrigatorias: presentes" in linhas
