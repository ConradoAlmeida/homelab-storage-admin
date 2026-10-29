from __future__ import annotations

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase
from django.urls import get_resolver, resolve

from core.ajuda import AJUDA, USE_CASES, ajuda_para, page_help

ROTAS_ESPERADAS = {
    "dashboard",
    "network_index",
    "containers",
    "container_logs",
    "users",
    "user_create",
    "user_password",
    "user_groups",
    "group_create",
    "shares",
    "share_create",
    "snapshots",
    "history_index",
    "history_share",
    "history_browse",
    "history_browse_root",
    "history_versions",
    "storage_index",
    "storage_smart",
    "backup_index",
    "backup_snapshots",
    "backup_snapshot_browse",
    "backup_disk_wizard",
    "backup_credentials",
    "gitea_backup",
    "arquivos_backup_index",
    "arquivos_job_new",
    "arquivos_job_edit",
    "arquivos_job",
    "cold_index",
    "cold_prepare",
    "backup_job_new",
    "backup_job_edit",
}


def nomes_de_rotas() -> set[str]:
    nomes: set[str] = set()

    def visitar(padroes):
        for padrao in padroes:
            if hasattr(padrao, "url_patterns"):
                visitar(padrao.url_patterns)
            elif padrao.name:
                nomes.add(padrao.name)

    visitar(get_resolver().url_patterns)
    return nomes


class AjudaTests(SimpleTestCase):
    def test_cobre_as_paginas_esperadas(self):
        self.assertLessEqual(ROTAS_ESPERADAS, set(AJUDA))
        self.assertEqual(set(USE_CASES), set(AJUDA))

    def test_todas_as_chaves_sao_rotas_reais(self):
        self.assertEqual(sorted(set(AJUDA) - nomes_de_rotas()), [])

    def test_capitulos_tem_titulo_e_conteudo(self):
        for rota, ajuda in AJUDA.items():
            with self.subTest(rota=rota):
                self.assertTrue(ajuda["title"])
                self.assertTrue(ajuda["summary"])
                self.assertTrue(ajuda["use_case"])
                self.assertTrue(ajuda["chapters"])
                for capitulo in ajuda["chapters"]:
                    self.assertTrue(capitulo["title"])
                    self.assertTrue(capitulo.get("text") or capitulo.get("bullets"))

    def test_rota_desconhecida_nao_tem_ajuda(self):
        self.assertIsNone(ajuda_para(None))
        self.assertIsNone(ajuda_para("rota_que_nao_existe"))

    def test_context_processor_resolve_a_rota(self):
        request = RequestFactory().get("/")
        request.resolver_match = resolve("/")
        self.assertEqual(page_help(request)["page_help"]["title"], "Dashboard")

    def test_context_processor_sem_resolver(self):
        request = RequestFactory().get("/")
        self.assertIsNone(page_help(request)["page_help"])

    def test_partial_renderiza_capitulos(self):
        html = render_to_string(
            "partials/page_help.html", {"page_help": AJUDA["dashboard"]}
        )
        self.assertIn("Ajuda desta página", html)
        self.assertIn("Saúde do sistema", html)
        self.assertIn("Backup de arquivos", html)
        self.assertIn("No dia a dia", html)
        self.assertIn("Visão consolidada do servidor", html)
        self.assertIn("Volumes mostram o uso das montagens do host.", html)
        self.assertNotIn("('title'", html)
        self.assertIn('class="page-help-chapter"', html)

    def test_partial_sem_ajuda_nao_renderiza(self):
        html = render_to_string("partials/page_help.html", {"page_help": None})
        self.assertEqual(html.strip(), "")

    def test_base_inclui_o_componente(self):
        from django.template.loader import get_template

        origem = get_template("base.html").template.source
        self.assertIn("partials/page_help.html", origem)
        self.assertIn("topbar", origem)
