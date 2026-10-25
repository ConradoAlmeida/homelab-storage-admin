import tempfile
from pathlib import Path
from unittest.mock import patch

from django.http import Http404
from django.test import SimpleTestCase, override_settings

from .views import _base, _safe_target, _snapshots


class SafeTargetTests(SimpleTestCase):
    def test_inside(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "pasta").mkdir()
            (base / "pasta" / "arquivo.txt").write_text("x")
            self.assertEqual(
                _safe_target(base, "pasta/arquivo.txt"),
                (base / "pasta" / "arquivo.txt").resolve(),
            )

    def test_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Http404):
                _safe_target(Path(directory), "../etc/passwd")

    def test_symlink_outside(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "share"
            base.mkdir()
            outside = Path(directory) / "fora.txt"
            outside.write_text("x")
            (base / "link").symlink_to(outside)
            with self.assertRaises(Http404):
                _safe_target(base, "link")


class SnapshotLayoutTests(SimpleTestCase):
    def test_snapshots_use_agent_snapdir(self):
        with tempfile.TemporaryDirectory() as directory:
            share = Path(directory) / "srv" / "docs"
            share.mkdir(parents=True)
            snapdir = share / ".snapshots"
            (snapdir / "@GMT-2026.10.25-12.00.00").mkdir(parents=True)
            info = {"name": "docs", "path": str(share), "snapdir": str(snapdir)}
            with patch("history.views.agent") as agent:
                agent.list_shares.return_value = [info]
                result = _snapshots("docs")
            self.assertEqual([item["name"] for item in result], ["@GMT-2026.10.25-12.00.00"])

    def test_base_uses_agent_snapdir_for_btrfs_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            share = Path(directory) / "docs"
            share.mkdir()
            snapdir = Path(directory) / ".snapshots" / "docs"
            (snapdir / "@GMT-2026.10.25-12.00.00").mkdir(parents=True)
            info = {"name": "docs", "path": str(share), "snapdir": str(snapdir)}
            with patch("history.views.agent") as agent:
                agent.list_shares.return_value = [info]
                base = _base("docs", "@GMT-2026.10.25-12.00.00")
            self.assertEqual(base, snapdir / "@GMT-2026.10.25-12.00.00")

    @override_settings(SNAPSHOT_ROOT="/mnt/nas/.snapshots")
    def test_old_agent_fallback_uses_settings_snapshot_root(self):
        with tempfile.TemporaryDirectory() as directory:
            share = Path(directory) / "docs"
            share.mkdir()
            info = {"name": "docs", "path": str(share)}
            with patch("history.views.agent") as agent:
                agent.list_shares.return_value = [info]
                self.assertEqual(
                    _snapshots("docs"),
                    [],
                )
