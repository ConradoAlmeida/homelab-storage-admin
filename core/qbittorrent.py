"""Cliente da API do qBittorrent que roda como container no homelab.

O painel fala com o serviço `qbittorrent` na rede do Compose. A WebUI não é
publicada no host: o celular usa esta página, e o download segue no Pi.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

from .agent import AgentError

QBIT_URL = os.environ.get("QBITTORRENT_URL", "http://qbittorrent:8080")
QBIT_USER = os.environ.get("QBITTORRENT_USER", "admin")
QBIT_PASSWORD = os.environ.get("QBITTORRENT_PASSWORD", "")

_JAR = CookieJar()
_LOCK = threading.Lock()
_MAGNET_RE = re.compile(r"(?:^|[?&])xt=urn:btih:([0-9a-zA-Z]{32,64})(?:&|$)", re.I)
_HASH_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_HOSTS = {"qbittorrent", "localhost", "127.0.0.1", "::1"}
_ATIVOS = {
    "downloading",
    "metaDL",
    "forcedDL",
    "stalledDL",
    "queuedDL",
    "checkingDL",
    "allocating",
    "moving",
}
_ESTADOS = {
    "downloading": "baixando",
    "metaDL": "lendo metadados",
    "forcedDL": "baixando",
    "stalledDL": "aguardando",
    "queuedDL": "na fila",
    "checkingDL": "verificando",
    "allocating": "alocando",
    "moving": "movendo",
    "pausedDL": "pausado",
    "stoppedDL": "pausado",
    "uploading": "enviando",
    "forcedUP": "enviando",
    "stalledUP": "concluído",
    "pausedUP": "concluído",
    "stoppedUP": "concluído",
    "queuedUP": "concluído",
    "checkingUP": "verificando",
    "error": "erro",
    "missingFiles": "arquivos ausentes",
}
_BAIXANDO_PAUSADO = {"pausedDL", "stoppedDL"}
_CONCLUIDOS = {
    "uploading",
    "forcedUP",
    "stalledUP",
    "pausedUP",
    "stoppedUP",
    "queuedUP",
    "checkingUP",
}


def _demo() -> bool:
    return os.environ.get("STORAGE_ADMIN_DEMO") == "1"


def _magnet_valido(valor: str) -> bool:
    if not valor or len(valor) > 4096 or any(caractere in valor for caractere in "\r\n\x00"):
        return False
    if not valor.lower().startswith("magnet:?"):
        return False
    return _MAGNET_RE.search(valor) is not None


def _base() -> str:
    bruto = (QBIT_URL or "").strip()
    parsed = urllib.parse.urlparse(bruto)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise AgentError("QBITTORRENT_URL inválida")
    if parsed.hostname not in _HOSTS:
        raise AgentError("qBittorrent só pode ser o container qbittorrent ou localhost")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AgentError("QBITTORRENT_URL não pode levar usuário, senha ou query")
    return bruto.rstrip("/")


def _abrir(method: str, path: str, data: dict | None = None, timeout: int = 20) -> tuple[int, str]:
    url = _base() + path
    body = None
    headers = {
        "Accept": "application/json, text/plain",
        "Referer": _base() + "/",
    }
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_JAR))
    try:
        with _LOCK:
            with opener.open(request, timeout=timeout) as response:
                return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return exc.code, raw
    except urllib.error.URLError as exc:
        raise AgentError(f"qBittorrent indisponível em {_base()}: {exc.reason}") from exc


def _login() -> bool:
    if not QBIT_PASSWORD:
        return False
    code, body = _abrir(
        "POST",
        "/api/v2/auth/login",
        {"username": QBIT_USER, "password": QBIT_PASSWORD},
    )
    return code == 200 and body.strip().lower().startswith("ok")


def disponivel() -> dict:
    if _demo():
        return {"available": True, "version": "v5.0.1", "reason": ""}
    try:
        code, body = _abrir("GET", "/api/v2/app/version")
    except AgentError as exc:
        return {"available": False, "version": "", "reason": str(exc)}
    if code == 403:
        if not _login():
            return {
                "available": False,
                "version": "",
                "reason": (
                    "O container qbittorrent exigiu login. Defina "
                    "QBITTORRENT_USER e QBITTORRENT_PASSWORD no ambiente do painel."
                ),
            }
        code, body = _abrir("GET", "/api/v2/app/version")
    if code == 200 and body.strip():
        return {"available": True, "version": body.strip(), "reason": ""}
    return {
        "available": False,
        "version": "",
        "reason": f"qBittorrent respondeu HTTP {code}.",
    }


def _post(caminhos: list[str], data: dict) -> tuple[int, str]:
    ultimo = (404, "")
    for caminho in caminhos:
        code, body = _abrir("POST", caminho, data, timeout=60)
        if code != 404:
            return code, body
        ultimo = (code, body)
    return ultimo


def _biblioteca_do_caminho(caminho: str, libraries: list[dict]) -> dict | None:
    if not caminho:
        return None
    real = os.path.realpath(caminho)
    for biblioteca in libraries:
        base = os.path.realpath(biblioteca.get("path") or "")
        if not base:
            continue
        if real == base or real.startswith(base + os.sep):
            return biblioteca
    return None


def _rotulo_bytes(valor: int) -> str:
    tamanho = float(max(0, int(valor or 0)))
    unidade = "B"
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if tamanho < 1024 or unidade == "TB":
            break
        tamanho /= 1024
    if unidade == "B":
        return f"{int(tamanho)} B"
    return f"{tamanho:.1f} {unidade}".replace(".", ",")


def _rotulo_eta(segundos) -> str:
    try:
        total = int(segundos)
    except (TypeError, ValueError):
        return ""
    if total < 0 or total > 8640000:
        return ""
    minutos, _resto = divmod(total, 60)
    horas, minutos = divmod(minutos, 60)
    if horas:
        return f"{horas} h {minutos} min"
    if minutos:
        return f"{minutos} min"
    return f"{total} s"


def _publico(item: dict, libraries: list[dict]) -> dict | None:
    biblioteca = _biblioteca_do_caminho(item.get("save_path") or "", libraries)
    if biblioteca is None:
        return None
    estado_bruto = item.get("state") or ""
    try:
        progresso = int(round(float(item.get("progress") or 0) * 100))
    except (TypeError, ValueError):
        progresso = 0
    progresso = max(0, min(100, progresso))
    concluido = estado_bruto in _CONCLUIDOS
    try:
        baixando = max(0, int(item.get("dlspeed") or 0))
    except (TypeError, ValueError):
        baixando = 0
    try:
        enviando = max(0, int(item.get("upspeed") or 0))
    except (TypeError, ValueError):
        enviando = 0
    return {
        "hash": (item.get("hash") or "").lower(),
        "name": item.get("name") or "sem nome",
        "progress": progresso,
        "progress_label": f"{progresso}%",
        "state": estado_bruto,
        "state_label": _ESTADOS.get(estado_bruto, estado_bruto or "desconhecido"),
        "download_speed": _rotulo_bytes(baixando) + "/s",
        "upload_speed": _rotulo_bytes(enviando) + "/s",
        "eta": "" if concluido else _rotulo_eta(item.get("eta")),
        "size": _rotulo_bytes(item.get("size") or 0),
        "library": biblioteca.get("name") or "",
        "active": estado_bruto in _ATIVOS
        or estado_bruto in {"uploading", "forcedUP"}
        or baixando > 0
        or enviando > 0,
        "can_pause": estado_bruto in _ATIVOS,
        "can_resume": estado_bruto in _BAIXANDO_PAUSADO,
    }


def listar(libraries: list[dict]) -> list[dict]:
    code, body = _abrir("GET", "/api/v2/torrents/info")
    if code != 200:
        raise AgentError(f"Não foi possível listar os torrents (HTTP {code})")
    try:
        itens = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AgentError("Resposta inválida do qBittorrent") from exc
    if not isinstance(itens, list):
        raise AgentError("Resposta inválida do qBittorrent")
    torrents = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        publico = _publico(item, libraries)
        if publico and _HASH_RE.match(publico["hash"]):
            torrents.append(publico)
    return torrents


def _demo_torrent() -> dict:
    return {
        "hash": "a" * 40,
        "name": "Exemplo",
        "progress": 42,
        "progress_label": "42%",
        "state": "downloading",
        "state_label": "baixando",
        "download_speed": "1,2 MB/s",
        "upload_speed": "80 KB/s",
        "eta": "12 min",
        "size": "2,0 GB",
        "library": "Filmes",
        "active": True,
        "can_pause": True,
        "can_resume": False,
    }


def estado(libraries: list[dict]) -> tuple[dict, list, str]:
    if _demo():
        return (
            {"available": True, "version": "v5.0.1", "reason": ""},
            [_demo_torrent()],
            "",
        )
    client = disponivel()
    torrents: list = []
    erro = ""
    if client.get("available") and libraries:
        try:
            torrents = listar(libraries)
        except AgentError as exc:
            erro = str(exc)
    return client, torrents, erro


def adicionar(magnet: str, library: str, libraries: list[dict]) -> dict:
    if _demo():
        destino = next((item for item in libraries if item.get("id") == library), None)
        return {
            "library": (destino or {}).get("name") or library,
            "path": (destino or {}).get("path") or "",
        }
    if not _magnet_valido(magnet or ""):
        raise AgentError("Link magnético inválido")
    destino = next((item for item in libraries if item.get("id") == library), None)
    if destino is None or not destino.get("path"):
        raise AgentError("Pasta de mídia inválida")
    client = disponivel()
    if not client.get("available"):
        raise AgentError(client.get("reason") or "qBittorrent indisponível")
    code, body = _abrir(
        "POST",
        "/api/v2/torrents/add",
        {
            "urls": magnet.strip(),
            "savepath": destino["path"],
            "category": "jellyfin",
            "paused": "false",
            "autoTMM": "false",
        },
        timeout=60,
    )
    if code != 200 or body.strip().lower().startswith("fail"):
        raise AgentError("qBittorrent recusou o link magnético")
    return {"library": destino.get("name") or library, "path": destino["path"]}


def _bruto(hash_torrent: str) -> dict:
    code, body = _abrir(
        "GET",
        "/api/v2/torrents/info?hashes=" + urllib.parse.quote(hash_torrent),
    )
    if code != 200:
        raise AgentError(f"Não foi possível consultar o torrent (HTTP {code})")
    try:
        itens = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AgentError("Resposta inválida do qBittorrent") from exc
    if not isinstance(itens, list) or not itens:
        raise AgentError("Torrent não encontrado")
    return itens[0]


def acao(torrent_hash: str, action: str, libraries: list[dict]) -> dict:
    if _demo():
        return {"hash": torrent_hash, "action": action}
    if action not in {"pause", "resume", "delete", "delete_files"}:
        raise AgentError("Ação inválida")
    if not _HASH_RE.match(torrent_hash or ""):
        raise AgentError("Hash inválido")
    client = disponivel()
    if not client.get("available"):
        raise AgentError(client.get("reason") or "qBittorrent indisponível")
    item = _bruto(torrent_hash)
    if _biblioteca_do_caminho(item.get("save_path") or "", libraries) is None:
        raise AgentError("Esse torrent não está numa pasta do Jellyfin")
    dados = {"hashes": torrent_hash}
    if action == "pause":
        code, _body = _post(["/api/v2/torrents/stop", "/api/v2/torrents/pause"], dados)
    elif action == "resume":
        code, _body = _post(["/api/v2/torrents/start", "/api/v2/torrents/resume"], dados)
    else:
        dados["deleteFiles"] = "true" if action == "delete_files" else "false"
        code, _body = _abrir("POST", "/api/v2/torrents/delete", dados, timeout=60)
    if code != 200:
        raise AgentError(f"qBittorrent recusou a ação (HTTP {code})")
    return {"hash": torrent_hash, "action": action}
