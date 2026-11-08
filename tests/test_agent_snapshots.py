from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("rsync") is None,
    reason="rsync nao esta no PATH",
)


def policy(agent, keep=5):
    share = Path(agent.STORAGE_ROOT) / "docs"
    share.mkdir(parents=True, exist_ok=True)
    snapdir = share / ".snapshots"
    agent.save_policies(
        {
            "docs": {
                "path": str(share),
                "enabled": True,
                "keep": keep,
                "backend": "rsync",
                "snapdir": str(snapdir),
            }
        }
    )
    return share, snapdir


def test_rsync_snapshot_uses_hardlink_for_unchanged_file(agent_module):
    agent = agent_module
    share, snapdir = policy(agent)
    (share / "unchanged.txt").write_text("same")
    first = agent.op_snapshot_create("docs")["name"]
    time.sleep(1.1)
    (share / "changed.txt").write_text("new")
    second = agent.op_snapshot_create("docs")["name"]
    assert first != second
    assert (snapdir / first / "unchanged.txt").is_file()
    assert (snapdir / second / "changed.txt").is_file()
    assert (
        (snapdir / first / "unchanged.txt").stat().st_ino
        == (snapdir / second / "unchanged.txt").stat().st_ino
    )


def test_rsync_snapshot_delete_only_named_snapshot(agent_module):
    agent = agent_module
    share, snapdir = policy(agent)
    (share / "a.txt").write_text("a")
    first = agent.op_snapshot_create("docs")["name"]
    time.sleep(1.1)
    second = agent.op_snapshot_create("docs")["name"]
    agent.op_snapshot_delete("docs", first)
    assert not (snapdir / first).exists()
    assert (snapdir / second).is_dir()


def test_rsync_prune_respects_keep(agent_module):
    agent = agent_module
    share, snapdir = policy(agent, keep=1)
    (share / "a.txt").write_text("a")
    first = agent.op_snapshot_create("docs")["name"]
    time.sleep(1.1)
    second = agent.op_snapshot_create("docs")["name"]
    names = [item.name for item in snapdir.iterdir() if item.is_dir()]
    assert first not in names
    assert second in names
    assert len(names) == 1


def test_snapshot_list_and_usage_report_backend_and_size(agent_module):
    agent = agent_module
    share, snapdir = policy(agent)
    (share / "old-only.txt").write_text("old")
    first = agent.op_snapshot_create("docs")["name"]
    (share / "old-only.txt").unlink()
    (share / "live.txt").write_text("live")
    time.sleep(1.1)
    agent.op_snapshot_create("docs")
    listed = agent.op_snapshot_list("docs")
    assert listed["backend"] == "rsync"
    assert listed["snapdir"] == str(snapdir)
    usage = agent.op_snapshot_usage()
    assert usage[0]["backend"] == "rsync"
    assert usage[0]["count"] == 2
    assert usage[0]["size"] >= len("old")


def test_snapshot_delete_rejects_traversal(agent_module):
    agent = agent_module
    policy(agent)
    with pytest.raises(agent.AgentError):
        agent.op_snapshot_delete("docs", "../fora")


def test_denylist_usage_does_not_scan_snapdir(agent_module, monkeypatch):
    agent = agent_module
    share, snapdir = policy(agent)
    agent.DENY_SNAPSHOT = {"docs"}
    monkeypatch.setattr(
        agent,
        "_snapshot_list",
        lambda path: pytest.fail("denylist nao pode varrer snapdir"),
    )
    usage = agent.op_snapshot_usage()
    assert usage[0]["share"] == "docs"
    assert usage[0]["enabled"] is False
    assert usage[0]["count"] == 0
    assert usage[0]["backend"] == "none"
    assert usage[0]["snapdir"] == ""


def gravar_smb(agent, nome="docs", quoted=False):
    path = Path(agent.STORAGE_ROOT) / nome
    path.mkdir(parents=True, exist_ok=True)
    caminho = f'"{path}"' if quoted else str(path)
    Path(agent.SMB_CONF).write_text(
        "[global]\n"
        "   workgroup = WORKGROUP\n"
        "\n"
        f"[{nome}]\n"
        f"    path = {caminho}\n"
        "    vfs objects = acl_xattr\n"
        "    comment = docs\n"
        "\n"
        "[fotos]\n"
        "    path = /mnt/nas/fotos\n"
        "    comment = intacto\n"
    )
    return path


def falso_run(agent, monkeypatch, falhar=None):
    comandos = []

    def fake_run(args, input_text=None, timeout=60):
        comandos.append(list(args))
        if args[:3] == ["btrfs", "subvolume", "show"]:
            raise agent.AgentError("nao e subvolume")
        if falhar and args and args[0] == falhar:
            raise agent.AgentError(f"{falhar} falhou")
        return ""

    monkeypatch.setattr(agent, "run", fake_run)
    monkeypatch.setattr(agent.shutil, "which", lambda command: f"/usr/bin/{command}")
    return comandos


def test_policy_save_configura_shadow_sem_mexer_nas_outras_secoes(agent_module, monkeypatch):
    agent = agent_module
    path = gravar_smb(agent)
    comandos = falso_run(agent, monkeypatch)
    resultado = agent.op_snapshot_policy_save(
        "docs", enabled=True, keep=4, create_now=False
    )
    texto = Path(agent.SMB_CONF).read_text()
    docs, fotos = texto.split("[fotos]", 1)
    snapdir = path / ".snapshots"
    assert resultado["enabled"] is True
    assert resultado["keep"] == 4
    assert resultado["created"] is None
    assert resultado["backend"] == "rsync"
    assert snapdir.is_dir()
    assert f"vfs objects = acl_xattr shadow_copy2" in docs
    assert f"shadow:snapdir = {snapdir}" in docs
    assert f"shadow:basedir = {path}" in docs
    assert "intacto" in fotos
    assert "shadow:" not in fotos
    assert "workgroup = WORKGROUP" in texto
    assert ["testparm", "-s"] in comandos
    assert ["smbcontrol", "smbd", "reload-config"] in comandos
    assert all(comando[0] != "rsync" for comando in comandos)
    policy = agent.load_policies()["docs"]
    assert policy["keep"] == 4
    assert policy["snapdir"] == str(snapdir)


def test_policy_save_cria_o_primeiro_snapshot(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    comandos = falso_run(agent, monkeypatch)
    resultado = agent.op_snapshot_policy_save(
        "docs", enabled=True, keep=3, create_now=True
    )
    assert resultado["created"].startswith("@GMT-")
    assert any(comando[0] == "rsync" for comando in comandos)


def test_policy_save_desativar_mantem_arquivos_e_reduzir_keep_nao_apaga(agent_module, monkeypatch):
    agent = agent_module
    path = gravar_smb(agent)
    falso_run(agent, monkeypatch)
    agent.op_snapshot_policy_save("docs", enabled=True, keep=4, create_now=False)
    snap = path / ".snapshots" / "@GMT-2026.01.01-00.00.00"
    snap.mkdir(parents=True)
    (snap / "arquivo.txt").write_text("x")
    agent.op_snapshot_policy_save("docs", enabled=False, keep=4)
    assert (snap / "arquivo.txt").read_text() == "x"
    docs, fotos = Path(agent.SMB_CONF).read_text().split("[fotos]", 1)
    assert "shadow:" not in docs
    assert "shadow_copy2" not in docs
    assert "acl_xattr" in docs
    assert "intacto" in fotos
    policy = agent.load_policies()["docs"]
    assert policy["enabled"] is False
    assert policy["snapdir"] == str(path / ".snapshots")
    agent.op_snapshot_policy_save("docs", enabled=True, keep=1, create_now=False)
    assert (snap / "arquivo.txt").read_text() == "x"
    assert agent.load_policies()["docs"]["keep"] == 1
    assert "shadow_copy2" in Path(agent.SMB_CONF).read_text().split("[fotos]", 1)[0]


def test_policy_save_preserva_snapdir_existente(agent_module, monkeypatch):
    agent = agent_module
    path = gravar_smb(agent)
    falso_run(agent, monkeypatch)
    agent.op_snapshot_policy_save("docs", enabled=True, keep=4, create_now=False)
    custom = path / "versoes"
    custom.mkdir()
    policy = agent.load_policies()
    policy["docs"]["snapdir"] = str(custom)
    agent.save_policies(policy)
    agent.op_snapshot_policy_save("docs", enabled=True, keep=2, create_now=False)
    assert agent.load_policies()["docs"]["snapdir"] == str(custom)
    assert f"shadow:snapdir = {custom}" in Path(agent.SMB_CONF).read_text()


def test_policy_save_aceita_caminho_entre_aspas(agent_module, monkeypatch):
    agent = agent_module
    path = gravar_smb(agent, quoted=True)
    falso_run(agent, monkeypatch)
    resultado = agent.op_snapshot_policy_save("docs", enabled=True, keep=2)
    assert resultado["path"] == str(path)
    assert f"shadow:basedir = {path}" in Path(agent.SMB_CONF).read_text()


def test_policy_save_recusa_keep_denylist_e_share_ausente(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    falso_run(agent, monkeypatch)
    original = Path(agent.SMB_CONF).read_text()
    for keep in (0, 169, "abc"):
        with pytest.raises(agent.AgentError):
            agent.op_snapshot_policy_save("docs", enabled=True, keep=keep)
    agent.DENY_SNAPSHOT = {"docs"}
    with pytest.raises(agent.AgentError, match="denylist"):
        agent.op_snapshot_policy_save("docs", enabled=True, keep=2)
    agent.DENY_SNAPSHOT = set()
    with pytest.raises(agent.AgentError, match="nao encontrado"):
        agent.op_snapshot_policy_save("ausente", enabled=True, keep=2)
    assert Path(agent.SMB_CONF).read_text() == original


def test_policy_save_btrfs_recusa_diretorio_que_nao_e_subvolume(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    agent.SNAPSHOT_BACKEND = "btrfs"
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: True)
    falso_run(agent, monkeypatch, falhar="btrfs")
    original = Path(agent.SMB_CONF).read_text()
    with pytest.raises(agent.AgentError, match="confirma"):
        agent.op_snapshot_policy_save("docs", enabled=True, keep=2)
    assert Path(agent.SMB_CONF).read_text() == original
    assert "docs" not in agent.load_policies()


def test_policy_save_btrfs_converte_com_confirmacao(agent_module, monkeypatch):
    agent = agent_module
    path = gravar_smb(agent)
    agent.SNAPSHOT_BACKEND = "btrfs"
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: True)
    comandos = falso_run(agent, monkeypatch, falhar="btrfs")

    def fake_convert(share, share_path):
        comandos.append(["convert", share, share_path])
        return None

    monkeypatch.setattr(agent, "_convert_directory_to_subvolume", fake_convert)
    monkeypatch.setattr(agent, "_path_is_subvolume", lambda p: False)

    resultado = agent.op_snapshot_policy_save(
        "docs", enabled=True, keep=3, confirmation="docs"
    )
    assert resultado["enabled"] is True
    assert resultado["backend"] == "btrfs"
    assert ["convert", "docs", str(path)] in comandos
    assert "shadow:snapdir" in Path(agent.SMB_CONF).read_text()
    assert agent.load_policies()["docs"]["enabled"] is True


def test_policy_save_btrfs_confirmacao_errada_nao_converte(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    agent.SNAPSHOT_BACKEND = "btrfs"
    monkeypatch.setattr(agent, "_fstype", lambda path: "btrfs")
    monkeypatch.setattr(agent.os.path, "ismount", lambda path: True)
    falso_run(agent, monkeypatch, falhar="btrfs")
    original = Path(agent.SMB_CONF).read_text()
    monkeypatch.setattr(
        agent,
        "_convert_directory_to_subvolume",
        lambda *args: pytest.fail("nao deve converter"),
    )
    with pytest.raises(agent.AgentError, match="Confirmacao incorreta"):
        agent.op_snapshot_policy_save(
            "docs", enabled=True, keep=2, confirmation="errado"
        )
    assert Path(agent.SMB_CONF).read_text() == original
    assert "docs" not in agent.load_policies()


def test_policy_save_restaura_smb_quando_testparm_falha(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    falso_run(agent, monkeypatch, falhar="testparm")
    original = Path(agent.SMB_CONF).read_text()
    with pytest.raises(agent.AgentError, match="restaurado"):
        agent.op_snapshot_policy_save("docs", enabled=True, keep=2)
    assert Path(agent.SMB_CONF).read_text() == original
    assert "docs" not in agent.load_policies()


def test_policy_save_informa_quando_o_snapshot_falha(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    falso_run(agent, monkeypatch, falhar="rsync")
    with pytest.raises(agent.AgentError, match="Politica salva"):
        agent.op_snapshot_policy_save("docs", enabled=True, keep=2, create_now=True)
    assert agent.load_policies()["docs"]["enabled"] is True
    assert "shadow:snapdir" in Path(agent.SMB_CONF).read_text()


def test_policy_save_segue_mesmo_se_o_reload_falhar(agent_module, monkeypatch):
    agent = agent_module
    gravar_smb(agent)
    falso_run(agent, monkeypatch, falhar="smbcontrol")
    resultado = agent.op_snapshot_policy_save("docs", enabled=True, keep=6)
    assert resultado["enabled"] is True
    assert resultado["keep"] == 6

