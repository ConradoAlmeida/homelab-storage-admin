import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .views import _base, _safe_target, _search, _snapshots


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


class SnapshotSearchTests(SimpleTestCase):
    def test_search_matches_name_and_hides_hidden_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "docs"
            (base / "sub").mkdir(parents=True)
            (base / "relatorio.pdf").write_text("a")
            (base / "sub" / "relatorio.txt").write_text("b")
            (base / "outro.txt").write_text("c")
            (base / ".oculto.txt").write_text("d")
            outside = Path(directory) / "fora.txt"
            outside.write_text("e")
            (base / "link.txt").symlink_to(outside)

            matches, total, truncated = _search(base, "relatorio")
            self.assertEqual(total, 2)
            self.assertFalse(truncated)
            self.assertEqual(
                [item["rel"] for item in matches],
                ["relatorio.pdf", "sub/relatorio.txt"],
            )
            self.assertTrue(all(not item["is_dir"] for item in matches))

    def test_search_wildcard_and_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for index in range(3):
                (base / f"{index}.pdf").write_text("x")
            (base / "nota.txt").write_text("x")

            matches, total, truncated = _search(base, "*.pdf", limit=2)
            self.assertEqual(total, 3)
            self.assertTrue(truncated)
            self.assertEqual(len(matches), 2)

    def test_search_path_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "sub").mkdir()
            (base / "sub" / "arquivo.txt").write_text("x")
            matches, total, _ = _search(base, "sub/arquivo")
            self.assertEqual(total, 1)
            self.assertEqual(matches[0]["rel"], "sub/arquivo.txt")


class SnapshotBrowseSearchViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="history-tester", password="test-password"
        )
        self.client.force_login(self.user)

    def test_browse_search_renders_results(self):
        with tempfile.TemporaryDirectory() as directory:
            share = Path(directory) / "docs"
            share.mkdir()
            snapdir = share / ".snapshots"
            snapshot = snapdir / "@GMT-2026.10.26-03.00.00"
            snapshot.mkdir(parents=True)
            (snapshot / "relatorio.pdf").write_text("conteudo")
            info = {
                "name": "docs",
                "path": str(share),
                "snapdir": str(snapdir),
            }
            with patch("history.views.agent") as agent:
                agent.list_shares.return_value = [info]
                response = self.client.get(
                    reverse(
                        "history_browse_root",
                        args=["docs", "@GMT-2026.10.26-03.00.00"],
                    ),
                    {"q": "relatorio"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Resultados para")
            self.assertContains(response, "relatorio.pdf")
            self.assertContains(response, "Baixar")
            self.assertContains(response, "Versões")
