import tempfile
from pathlib import Path

from django.http import Http404
from django.test import SimpleTestCase

from .views import _safe_target


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
