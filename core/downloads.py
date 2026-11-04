"""Downloads de torrent para as pastas de mídia do Jellyfin."""

from __future__ import annotations

import hashlib
import hmac
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from . import qbittorrent
from .agent import AgentError, agent
from .forms import TorrentAddForm
from .models import AuditLog, definir_token_da_api, token_da_api
from .view_base import AgentPostView, AgentTemplateView, AgentView


class ExigeJellyfinMixin:
    """A página só existe no host em que o container do Jellyfin está instalado."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        from core.context_processors import capacidades_do_host

        if not capacidades_do_host().get("jellyfin"):
            messages.error(request, "O Jellyfin não está instalado neste servidor.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)


def _bibliotecas(overview) -> list:
    libraries = overview.get("libraries") if isinstance(overview, dict) else []
    if not isinstance(libraries, list):
        return []
    return [item for item in libraries if isinstance(item, dict)]


def _visao():
    bruto = agent.torrent_overview()
    if not isinstance(bruto, dict):
        bruto = {}
    libraries = _bibliotecas(bruto)
    client, torrents, erro = qbittorrent.estado(libraries)
    return {
        "libraries": libraries,
        "libraries_error": bruto.get("libraries_error")
        or (
            ""
            if libraries
            else "Nenhuma pasta de mídia encontrada na configuração do Jellyfin."
        ),
        "client": client if isinstance(client, dict) else {},
        "torrents": torrents if isinstance(torrents, list) else [],
        "error": erro or "",
        "active": any(isinstance(item, dict) and item.get("active") for item in (torrents or [])),
    }


def _auditar(request, action, target):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        target=target,
        ip=request.META.get("REMOTE_ADDR"),
    )


def _administrador(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and (user.is_superuser or user.username == "admin")
    )


def _token_aceitavel(valor: str) -> bool:
    if not valor or valor != valor.strip():
        return False
    if any(caractere.isspace() or caractere in "\r\n\x00" for caractere in valor):
        return False
    return 16 <= len(valor) <= 256


class TorrentsView(ExigeJellyfinMixin, AgentTemplateView):
    template_name = "torrents.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "overview": None,
                "error": None,
                "form": None,
                "pode_ver_token": _administrador(self.request.user),
                "token_existe": False,
                "token_revelado": "",
                "token_erro": "",
            }
        )
        try:
            overview = _visao()
        except AgentError as exc:
            context["error"] = str(exc)
            return context
        context["overview"] = overview
        libraries = overview.get("libraries") if isinstance(overview, dict) else []
        client = overview.get("client") if isinstance(overview, dict) else {}
        if (
            isinstance(client, dict)
            and client.get("available")
            and isinstance(libraries, list)
            and libraries
        ):
            context["form"] = TorrentAddForm(libraries=libraries)
        context["token_existe"] = bool(token_da_api())
        return context

    def post(self, request):
        context = self.get_context_data()
        if not context["pode_ver_token"]:
            context["token_erro"] = "Só o administrador consulta o token."
            return self.render_to_response(context)
        senha = request.POST.get("password") or ""
        if not request.user.check_password(senha):
            context["token_erro"] = "Senha do administrador incorreta."
            return self.render_to_response(context)
        acao = request.POST.get("acao") or "consultar"
        if acao in {"trocar", "criar"}:
            novo = request.POST.get("token") or ""
            if not _token_aceitavel(novo):
                context["token_erro"] = (
                    "O token novo precisa ter de 16 a 256 caracteres, sem espaços."
                )
                return self.render_to_response(context)
            ja_tinha = bool(token_da_api())
            definir_token_da_api(novo)
            context["token_revelado"] = novo
            context["token_existe"] = True
            AuditLog.objects.create(
                actor=request.user,
                action="torrent.token.replace",
                target="TORRENT_API_TOKEN",
                ip=request.META.get("REMOTE_ADDR") or None,
            )
            messages.success(
                request,
                "Token da API atualizado." if ja_tinha else "Token da API criado.",
            )
        else:
            valor = token_da_api()
            if not valor:
                context["token_erro"] = "Ainda não há token. Use Criar token."
                return self.render_to_response(context)
            context["token_revelado"] = valor
            AuditLog.objects.create(
                actor=request.user,
                action="torrent.token.view",
                target="TORRENT_API_TOKEN",
                ip=request.META.get("REMOTE_ADDR") or None,
            )
        resposta = self.render_to_response(context)
        resposta["Cache-Control"] = "no-store"
        return resposta


class TorrentStatusView(ExigeJellyfinMixin, AgentView):
    def get(self, request):
        try:
            overview = _visao()
        except AgentError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
        return JsonResponse(
            {
                "active": bool(overview.get("active")),
                "torrents": overview.get("torrents") or [],
            }
        )


class TorrentAddView(ExigeJellyfinMixin, AgentView):
    def post(self, request):
        try:
            overview = _visao()
        except AgentError as exc:
            messages.error(request, str(exc))
            return redirect("torrents")
        form = TorrentAddForm(request.POST, libraries=overview.get("libraries"))
        pagina = {
            "overview": overview,
            "error": None,
            "form": form,
            "pode_ver_token": _administrador(request.user),
            "token_existe": bool(token_da_api()),
            "token_revelado": "",
            "token_erro": "",
        }
        if not form.is_valid():
            return render(request, "torrents.html", pagina)
        data = form.cleaned_data
        try:
            resultado = qbittorrent.adicionar(
                data["magnet"], data["library"], _bibliotecas(overview)
            )
        except AgentError as exc:
            form.add_error(None, str(exc))
            return render(request, "torrents.html", pagina)
        _auditar(request, "torrent.add", resultado.get("library") or data["library"])
        messages.success(
            request,
            f"Torrent adicionado em {resultado.get('library') or 'a pasta escolhida'}.",
        )
        return redirect("torrents")


def _pagina_torrents(request, overview, *, organizacao=None, form=None):
    libraries = overview.get("libraries") if isinstance(overview, dict) else []
    client = overview.get("client") if isinstance(overview, dict) else {}
    if form is None and (
        isinstance(client, dict)
        and client.get("available")
        and isinstance(libraries, list)
        and libraries
    ):
        form = TorrentAddForm(libraries=libraries)
    return {
        "overview": overview,
        "error": None,
        "form": form,
        "organizacao": organizacao,
        "pode_ver_token": _administrador(request.user),
        "token_existe": bool(token_da_api()),
        "token_revelado": "",
        "token_erro": "",
    }


class TorrentOrganizeView(ExigeJellyfinMixin, AgentPostView):
    def post(self, request):
        organizacao = None
        try:
            overview = _visao()
            organizacao = qbittorrent.organizar(_bibliotecas(overview))
        except AgentError as exc:
            messages.error(request, str(exc))
            try:
                overview = _visao()
            except AgentError as exc_visao:
                messages.error(request, str(exc_visao))
                return redirect("torrents")
        else:
            feitos = len(organizacao.get("feitos") or [])
            padrao = len(organizacao.get("ja_no_padrao") or [])
            falhas = len(organizacao.get("nao_feitos") or [])
            _auditar(
                request,
                "torrent.organize",
                f"{feitos} feitos, {padrao} já no padrão, {falhas} não feitos",
            )
        pagina = _pagina_torrents(request, overview, organizacao=organizacao)
        return render(request, "torrents.html", pagina)


class TorrentActionView(ExigeJellyfinMixin, AgentPostView):
    def post(self, request):
        torrent_hash = request.POST.get("hash", "")
        action = request.POST.get("action", "")
        try:
            overview = _visao()
            qbittorrent.acao(torrent_hash, action, _bibliotecas(overview))
        except AgentError as exc:
            messages.error(request, str(exc))
        else:
            _auditar(request, f"torrent.{action}", torrent_hash)
            if action == "delete_files":
                messages.success(request, "Torrent removido e arquivos apagados.")
            elif action == "delete":
                messages.success(request, "Torrent removido da fila. Os arquivos permanecem.")
            elif action == "pause":
                messages.success(request, "Download pausado.")
            elif action == "resume":
                messages.success(request, "Download retomado.")
        return redirect("torrents")


def _token_confere(request) -> bool:
    esperado = token_da_api()
    header = request.META.get("HTTP_AUTHORIZATION", "")
    partes = header.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return False
    apresentado = partes[1].strip()
    if not esperado or not apresentado or any(caractere in apresentado for caractere in "\r\n"):
        return False
    return hmac.compare_digest(
        hashlib.sha256(apresentado.encode()).digest(),
        hashlib.sha256(esperado.encode()).digest(),
    )


def _recusa_api(request):
    if not token_da_api():
        return JsonResponse({"error": "Não encontrado."}, status=404)
    if not _token_confere(request):
        return JsonResponse({"error": "Token inválido."}, status=401)
    from core.context_processors import capacidades_do_host

    if not capacidades_do_host().get("jellyfin"):
        return JsonResponse(
            {"error": "O Jellyfin não está instalado neste servidor."},
            status=404,
        )
    return None


def _bibliotecas_validas(overview) -> list:
    return [
        item
        for item in _bibliotecas(overview)
        if item.get("id") and item.get("name") and item.get("path")
    ]


def _escolher_biblioteca(valor: str, libraries: list) -> dict | None:
    pedido = (valor or "").strip()
    if not pedido:
        return None
    por_id = [item for item in libraries if item.get("id") == pedido]
    if len(por_id) == 1:
        return por_id[0]
    por_nome = [item for item in libraries if item.get("name") == pedido]
    if len(por_nome) == 1:
        return por_nome[0]
    return None


def _corpo_json(request):
    bruto = request.body or b""
    if len(bruto) > 8192:
        return None
    try:
        payload = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _mensagem_form(form) -> str:
    for erros in form.errors.values():
        if erros:
            return str(erros[0])
    return "Dados inválidos."


def _resposta_qbit(exc: AgentError) -> JsonResponse:
    texto = str(exc)
    if texto == "torrent já existe na lista":
        return JsonResponse({"error": texto}, status=409)
    if texto in {"Link magnético inválido", "Pasta de mídia inválida"}:
        return JsonResponse({"error": texto}, status=400)
    return JsonResponse({"error": texto}, status=503)


class _TorrentApiBase(View):
    """Envio por Bearer. Sessão e CSRF não autorizam esta rota."""

    def dispatch(self, request, *args, **kwargs):
        recusa = _recusa_api(request)
        if recusa is not None:
            return recusa
        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
class TorrentBibliotecasApiView(_TorrentApiBase):
    http_method_names = ["get"]

    def get(self, request):
        try:
            overview = agent.torrent_overview()
        except AgentError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
        bibliotecas = [
            {"id": item["id"], "name": item["name"]} for item in _bibliotecas_validas(overview)
        ]
        return JsonResponse({"libraries": bibliotecas})


@method_decorator(csrf_exempt, name="dispatch")
class TorrentEnvioApiView(_TorrentApiBase):
    http_method_names = ["post"]

    def post(self, request):
        payload = _corpo_json(request)
        if payload is None:
            return JsonResponse({"error": "JSON inválido."}, status=400)
        magnet = payload.get("magnet", "")
        library = payload.get("library", "")
        if not isinstance(magnet, str) or not isinstance(library, str):
            return JsonResponse({"error": "JSON inválido."}, status=400)
        try:
            overview = agent.torrent_overview()
        except AgentError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
        libraries = _bibliotecas_validas(overview)
        destino = _escolher_biblioteca(library, libraries)
        if destino is None:
            return JsonResponse({"error": "Pasta de mídia inválida."}, status=400)
        form = TorrentAddForm(
            {"magnet": magnet, "library": destino["id"]},
            libraries=libraries,
        )
        if not form.is_valid():
            return JsonResponse({"error": _mensagem_form(form)}, status=400)
        try:
            resultado = qbittorrent.adicionar(
                form.cleaned_data["magnet"], destino["id"], libraries
            )
        except AgentError as exc:
            return _resposta_qbit(exc)
        AuditLog.objects.create(
            actor=None,
            action="torrent.add",
            target=resultado.get("library") or destino.get("name") or destino["id"],
            detail="api",
            ip=request.META.get("REMOTE_ADDR") or None,
        )
        return JsonResponse(
            {"library": resultado.get("library") or destino.get("name")},
            status=201,
        )
