#!/usr/bin/env python3
"""Gera screenshots da página Usuários (homelab e moya) para evidência visual."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path("/opt/cursor/artifacts")
BASE = "http://127.0.0.1:8765"
UV = str(Path.home() / ".local/bin/uv")
VIEWPORTS = (
    ("desktop_1920", {"width": 1920, "height": 1080}),
    ("desktop_1280", {"width": 1280, "height": 800}),
    ("mobile", {"width": 390, "height": 844}),
)


def run_uv(*args: str, env: dict | None = None) -> None:
    subprocess.check_call([UV, "run", *args], cwd=ROOT, env=env)


def wait_http(path: str, timeout: float = 45.0) -> None:
    import urllib.request

    fim = time.monotonic() + timeout
    url = BASE + path
    while time.monotonic() < fim:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return
        except OSError:
            time.sleep(0.4)
    raise RuntimeError(f"Servidor não respondeu em {url}")


def ensure_admin(env: dict) -> None:
    run_uv("manage.py", "migrate", "--noinput", env=env)
    run_uv(
        "manage.py",
        "shell",
        "-c",
        (
            "from django.contrib.auth import get_user_model; "
            "User = get_user_model(); "
            "User.objects.filter(username='admin').exists() or "
            "User.objects.create_superuser('admin', 'admin@local', 'admin-demo')"
        ),
        env=env,
    )


def assert_card_layout(page, perfil: str, label: str) -> None:
    """Confere rodapé completo e grade com mais de uma coluna em desktop."""
    card = page.locator(".person-card").first
    card.wait_for(timeout=20000)
    footer = card.locator(".person-actions")
    buttons = footer.locator(".btn")
    count = buttons.count()
    if count < 4:
        raise RuntimeError(f"{perfil}/{label}: esperava 4 ações, vi {count}")
    card_box = card.bounding_box()
    for i in range(count):
        btn = buttons.nth(i)
        box = btn.bounding_box()
        if not box or not card_box:
            raise RuntimeError(f"{perfil}/{label}: botão {i} sem caixa")
        if box["x"] + box["width"] > card_box["x"] + card_box["width"] + 0.5:
            raise RuntimeError(f"{perfil}/{label}: botão {i} cortado à direita")
    if "desktop" in label:
        cols = page.locator(".person-grid .person-card").count()
        grid = page.locator(".person-grid").bounding_box()
        if grid and grid["width"] > 500 and cols >= 2:
            second = page.locator(".person-card").nth(1).bounding_box()
            first = page.locator(".person-card").nth(0).bounding_box()
            if second and first and second["x"] <= first["x"] + 10:
                raise RuntimeError(
                    f"{perfil}/{label}: grade em uma coluna com espaço para várias"
                )


def shot(perfil: str, env: dict) -> None:
    from playwright.sync_api import sync_playwright

    server = subprocess.Popen(
        [UV, "run", "manage.py", "runserver", "127.0.0.1:8765", "--noreload"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        wait_http("/login/")
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for label, viewport in VIEWPORTS:
                page = browser.new_page(viewport=viewport)
                page.goto(f"{BASE}/login/")
                page.fill('input[name="username"]', "admin")
                page.fill('input[name="password"]', "admin-demo")
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle")
                page.goto(f"{BASE}/usuarios/")
                assert_card_layout(page, perfil, label)
                out = ARTIFACTS / f"usuarios_{perfil}_{label}_depois.png"
                page.screenshot(path=str(out), full_page=True)
                if label == "desktop_1920":
                    import shutil

                    shutil.copy(out, ARTIFACTS / f"usuarios_{perfil}_desktop_depois.png")
                page.close()
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    base_env = os.environ.copy()
    db = ARTIFACTS / "screenshot-usuarios.sqlite3"
    base_env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "DJANGO_DEBUG": "1",
            "STORAGE_ADMIN_DEMO": "1",
            "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "DJANGO_SQLITE_PATH": str(db),
            "PATH": f"{Path.home()}/.local/bin:" + base_env.get("PATH", ""),
        }
    )
    ensure_admin(base_env)
    shot(
        "homelab",
        {**base_env, "CREDENTIALS_MANAGE_USERS": "0", "SITE_NAME": "Homelab Storage"},
    )
    shot(
        "moya",
        {
            **base_env,
            "CREDENTIALS_MANAGE_USERS": "1",
            "CREDENTIALS_URL": "http://credenciais",
            "CREDENTIALS_API_TOKEN": "demo",
            "CREDENTIALS_APP": "storage",
            "SITE_NAME": "Moya Storage",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
