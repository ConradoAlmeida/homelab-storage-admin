from __future__ import annotations

from pathlib import Path

from core.homelab_config import carregar_arquivo, texto_host_env, texto_sync_env, texto_unit
from core.homelab_doctor import analisar, drift, resumo

TOML = """\
[host]
nome = "mini"
ssh = "conrado@mini"
lan_ip = "10.0.0.2"
repo = "{repo}"

[app]
site_name = "Mini"
bind_addr = "10.0.0.2"

[caminhos]
dados = "{tmp}/dados"
backup = "{tmp}/backup"
config = "{tmp}/etc"

[armazenamento]
proprietario = "conrado"
mounts = []

[rotas]
apps = "deploy/mini/apps.env"

[features]
{extras}
"""


def faz_host(tmp_path: Path, *, extras: str = "", modo: int = 0o600):
    repo = tmp_path / "repo"
    (repo / "deploy" / "mini").mkdir(parents=True)
    (repo / "deploy" / "mini" / "apps.env").write_text("", encoding="utf-8")
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(
        TOML.replace("{tmp}", str(tmp_path)).replace("{repo}", str(repo)).replace(
            "{extras}", extras
        ),
        encoding="utf-8",
    )
    cfg = carregar_arquivo(arquivo)
    config = tmp_path / "etc"
    config.mkdir()
    (config / "host.env").write_text(texto_host_env(cfg), encoding="utf-8")
    (config / "sync.env").write_text(texto_sync_env(cfg), encoding="utf-8")
    env = repo / ".env"
    env.write_text("DJANGO_SECRET_KEY=" + "a" * 64 + "\n", encoding="utf-8")
    env.chmod(modo)
    return cfg, config, env


def sem_erros(achados) -> list[str]:
    return [a.mensagem for a in achados if a.nivel == "erro"]


def test_host_pronto_nao_tem_erro(tmp_path):
    cfg, config, env = faz_host(tmp_path)
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x"
    )
    assert sem_erros(achados) == []
    assert "erros: 0" in resumo(achados)


def test_drift_do_sync_env_e_erro(tmp_path):
    cfg, config, env = faz_host(tmp_path)
    (config / "sync.env").write_text("DNS_MODE=outro\n", encoding="utf-8")
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x"
    )
    erros = sem_erros(achados)
    assert any("sync.env difere do host.toml" in e for e in erros)
    assert any("render mini --write" in e for e in erros)


def test_falta_do_host_env_pede_render(tmp_path):
    cfg, config, env = faz_host(tmp_path)
    (config / "host.env").unlink()
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x"
    )
    assert any("falta host.env" in e for e in sem_erros(achados))


def test_env_com_modo_largo_e_segredo_de_exemplo(tmp_path):
    cfg, config, env = faz_host(tmp_path, modo=0o644)
    env.write_text("DJANGO_SECRET_KEY=troque-por-uma-chave-aleatoria-longa\n")
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x"
    )
    erros = sem_erros(achados)
    assert any("modo 644" in e for e in erros)
    assert any("DJANGO_SECRET_KEY" in e for e in erros)


def test_dependencia_obrigatoria_ausente_e_erro(tmp_path):
    cfg, config, env = faz_host(tmp_path, extras="samba = true")
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: None
    )
    erros = sem_erros(achados)
    assert any("falta 'pdbedit'" in e for e in erros)
    assert any("apt install samba" in e for e in erros)


def test_opcional_ausente_e_so_aviso(tmp_path):
    cfg, config, env = faz_host(tmp_path, extras="snapshots = true")
    achados = analisar(
        cfg,
        config_dir=config,
        env_file=env,
        which=lambda nome: None if nome == "btrfs" else "/usr/bin/x",
    )
    assert sem_erros(achados) == []
    assert any(a.nivel == "aviso" and "btrfs" in a.mensagem for a in achados)


def test_unit_de_boot_fora_de_sync(tmp_path):
    extras = (
        '[boot]\nunit = "mini.service"\ndescricao = "Mini stacks"\n'
        'esperar_mounts = []\nantes = []\ndepois = []\n'
    )
    cfg, config, env = faz_host(tmp_path, extras=extras)
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    # Ainda nao instalada: aviso, nao erro.
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x",
        unit_dir=unit_dir,
    )
    assert sem_erros(achados) == []
    assert any("nao instalada" in a.mensagem for a in achados)

    (unit_dir / "mini.service").write_text(texto_unit(cfg), encoding="utf-8")
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x",
        unit_dir=unit_dir,
    )
    assert sem_erros(achados) == []

    (unit_dir / "mini.service").write_text("velho\n", encoding="utf-8")
    achados = analisar(
        cfg, config_dir=config, env_file=env, which=lambda _n: "/usr/bin/x",
        unit_dir=unit_dir,
    )
    assert any("difere do host.toml" in e for e in sem_erros(achados))


def test_drift_so_avisa_o_que_esta_instalado(tmp_path):
    cfg, config, _env = faz_host(tmp_path)
    assert drift(cfg, config_dir=config) == []
    (config / "host.env").write_text("SITE_NAME=\"Outro\"\n", encoding="utf-8")
    achados = drift(cfg, config_dir=config)
    assert any("host.env difere" in a.mensagem for a in achados)


def test_drift_ignora_host_sem_render(tmp_path):
    cfg, _config, _env = faz_host(tmp_path)
    # No CI/desktop nao ha /etc do host: comparar nada nao pode virar aviso.
    assert drift(cfg, config_dir=tmp_path / "nao-existe") == []
