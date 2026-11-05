"""Cliente da API do qBittorrent que roda como container no homelab.

No Pi o container usa a rede do host. O painel fala com o nome `qbittorrent`,
que o overlay aponta para o gateway do Docker, na porta da WebUI (8090).
A 8080 permanece com o serviço que já escuta no Pi. O celular usa esta página.
"""

from __future__ import annotations

import base64
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
JA_EXISTE = "torrent já existe na lista"
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
    "checkingResumeData": "verificando",
    "checkingRI": "verificando",
    "checkingRD": "verificando",
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
_DOMINIO_INDEXADOR = re.compile(
    r"^(?:www\.)?(?:https?://)?[\w.-]+\."
    r"(?:org|com|net|mx|ag|am|re|to|io|info|xyz|cc|tv|st|ws|biz|ru|su|la)"
    r"[\s._-]*",
    re.I,
)
_CORTE_TITULO = re.compile(
    r"(?:\s+|^)(?:S\d{2}|Season\s*\d+|Complete|1080p?|720p?|2160p?|WEB-DL|BluRay|WEBRip|"
    r"NF|AMZN|ATVP|ITA|SPA|MULTI|DDP|h264|h265|x264|x265)\b",
    re.I,
)
_ANO_PAREN = re.compile(r"\((19|20)\d{2}\)")
_ANO_SOLTO = re.compile(r"\b((19|20)\d{2})\b")
_OVERRIDES_TITULO = {
    "Colony": "Colony (2016)",
    "L Eternauta": "O Eternauta (2025)",
    "Eternauta": "O Eternauta (2025)",
    "Station Eleven": "Station Eleven (2021)",
    "The Walking Dead Daryl Dixon": "The Walking Dead Daryl Dixon (2023)",
    "The Walking Dead The Ones Who Live": "The Walking Dead The Ones Who Live (2024)",
}
_ESTADOS_INSTAVEIS = frozenset(
    {
        "moving",
        "checkingResumeData",
        "checkingDL",
        "checkingUP",
        "checkingRI",
        "checkingRD",
        "metaDL",
    }
)
_MSG_ESTADO_INSTAVEL = (
    "Torrent em movimentação/verificação; aguarde o estado estabilizar antes de remover."
)
_SEM_ANO_MOTIVO = "Sem ano no título e sem override"
_AVISO_RESIDUO = "Resíduo grande, sem torrent"
_RESIDUO_MIN_BYTES = 1024**3
_ESTADOS_TORRENT_CONCLUIDO = frozenset(
    {"uploading", "stalledUP", "pausedUP", "stoppedUP"}
)
_MSG_TORRENT_REMOVER_LISTA = (
    "Torrent concluído — remova-o da lista (manter arquivos) e rode o organizador de novo."
)
_MSG_TORRENT_AGUARDE_DOWNLOAD = "Torrent em download — aguarde concluir."


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
        "size_bytes": max(0, int(item.get("size") or 0)),
        "download_bps": baixando,
        "upload_bps": enviando,
        "library": biblioteca.get("name") or "",
        "active": estado_bruto in _ATIVOS
        or estado_bruto in {"uploading", "forcedUP"}
        or baixando > 0
        or enviando > 0,
        "can_pause": estado_bruto in _ATIVOS,
        "can_resume": estado_bruto in _BAIXANDO_PAUSADO,
        "can_delete": estado_bruto not in _ESTADOS_INSTAVEIS,
        "delete_blocked_message": (
            _MSG_ESTADO_INSTAVEL if estado_bruto in _ESTADOS_INSTAVEIS else ""
        ),
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
        "can_delete": True,
        "delete_blocked_message": "",
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


def _infohash(magnet: str) -> str:
    match = _MAGNET_RE.search(magnet or "")
    if not match:
        return ""
    bruto = match.group(1)
    if re.fullmatch(r"[0-9a-fA-F]{40}", bruto) or re.fullmatch(r"[0-9a-fA-F]{64}", bruto):
        return bruto.lower()
    if re.fullmatch(r"[A-Za-z2-7]{32}", bruto):
        try:
            return base64.b32decode(bruto.upper()).hex()
        except ValueError:
            return ""
    return ""


def _ja_na_lista(infohash: str) -> bool:
    if not infohash or not _HASH_RE.match(infohash):
        return False
    code, body = _abrir(
        "GET",
        "/api/v2/torrents/info?hashes=" + urllib.parse.quote(infohash),
    )
    if code != 200:
        return False
    try:
        itens = json.loads(body)
    except json.JSONDecodeError:
        return False
    if not isinstance(itens, list):
        return False
    alvo = infohash.lower()
    return any(
        isinstance(item, dict) and (item.get("hash") or "").lower() == alvo for item in itens
    )


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
    infohash = _infohash(magnet.strip())
    if _ja_na_lista(infohash):
        raise AgentError(JA_EXISTE)
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
        if _ja_na_lista(infohash):
            raise AgentError(JA_EXISTE)
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
    estado = item.get("state") or ""
    if action in {"delete", "delete_files"} and estado in _ESTADOS_INSTAVEIS:
        raise AgentError(_MSG_ESTADO_INSTAVEL)
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


def _limpar_titulo(bruto: str) -> tuple[str, int | None]:
    texto = (bruto or "").strip()
    texto = _DOMINIO_INDEXADOR.sub("", texto)
    texto = re.sub(r"[._-]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    corte = _CORTE_TITULO.search(texto)
    if corte:
        texto = texto[: corte.start()].strip()
    ano = None
    match = _ANO_PAREN.search(texto)
    if match:
        ano = int(match.group(0)[1:-1])
        texto = (texto[: match.start()] + texto[match.end() :]).strip()
    else:
        match = _ANO_SOLTO.search(texto)
        if match:
            ano = int(match.group(1))
            texto = texto[: match.start()].strip()
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto, ano


def _sem_ano_pasta(nome_pasta: str) -> bool:
    titulo, ano = _limpar_titulo(nome_pasta)
    if not titulo:
        return False
    if titulo in _OVERRIDES_TITULO:
        return False
    return ano is None


def _tamanho_arquivos_diretorio(caminho: str) -> int:
    total = 0
    try:
        for raiz, _dirs, arquivos in os.walk(caminho, followlinks=False):
            for nome in arquivos:
                caminho_arquivo = os.path.join(raiz, nome)
                if os.path.islink(caminho_arquivo):
                    continue
                try:
                    total += os.path.getsize(caminho_arquivo)
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _aviso_residuo_pasta(pasta: str, tem_torrent: bool) -> str:
    if tem_torrent:
        return ""
    if _tamanho_arquivos_diretorio(pasta) >= _RESIDUO_MIN_BYTES:
        return _AVISO_RESIDUO
    return ""


def _torrent_organizavel_e_feedback(item: dict) -> tuple[bool, str]:
    try:
        progresso_ok = float(item.get("progress") or 0) >= 1
    except (TypeError, ValueError):
        progresso_ok = False
    estado = item.get("state") or ""
    if progresso_ok and estado in _ESTADOS_TORRENT_CONCLUIDO:
        return True, _MSG_TORRENT_REMOVER_LISTA
    return False, _MSG_TORRENT_AGUARDE_DOWNLOAD


def alvo_da_pasta(nome_torrent: str) -> str | None:
    """Nome de pasta Jellyfin a partir do nome do torrent; None se não der para inferir."""
    titulo, ano = _limpar_titulo(nome_torrent)
    if not titulo:
        return None
    if titulo in _OVERRIDES_TITULO:
        return _OVERRIDES_TITULO[titulo]
    if ano is not None:
        return f"{titulo} ({ano})"
    return titulo


def _save_path_no_jellyfin(save_path: str) -> bool:
    if not save_path:
        return False
    real = os.path.realpath(save_path)
    base = os.path.realpath(os.environ.get("JELLYFIN_ROOT", "/mnt/jellyfin"))
    return real == base or real.startswith(base + os.sep)


def _caminho_antigo(save_path: str, content_path: str) -> str | None:
    if not _save_path_no_jellyfin(save_path):
        return None
    try:
        entradas = os.listdir(save_path)
    except OSError:
        return None
    alvo = (content_path or "").rstrip(os.sep)
    if not alvo:
        return None
    nome = os.path.basename(alvo)
    if nome in entradas:
        return nome
    try:
        relativo = os.path.relpath(alvo, save_path)
    except ValueError:
        return None
    if relativo.startswith(".."):
        return None
    partes = relativo.split(os.sep)
    if len(partes) >= 2:
        return partes[0]
    pai = os.path.dirname(relativo)
    return pai if pai and pai != "." else None


def _listar_bruto() -> list[dict]:
    code, body = _abrir("GET", "/api/v2/torrents/info")
    if code != 200:
        raise AgentError(f"Não foi possível listar os torrents (HTTP {code})")
    try:
        itens = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AgentError("Resposta inválida do qBittorrent") from exc
    if not isinstance(itens, list):
        raise AgentError("Resposta inválida do qBittorrent")
    return [item for item in itens if isinstance(item, dict)]


def _mapa_torrents_por_pasta(libraries: list[dict]) -> dict[tuple[str, str], dict]:
    if _demo():
        return {}
    mapa: dict[tuple[str, str], dict] = {}
    for item in _listar_bruto():
        save_path = item.get("save_path") or ""
        biblioteca = _biblioteca_do_caminho(save_path, libraries)
        if biblioteca is None:
            continue
        base = os.path.realpath(biblioteca.get("path") or "")
        if not base:
            continue
        nomes = []
        pasta = _caminho_antigo(save_path, item.get("content_path") or "")
        if pasta:
            nomes.append(pasta)
        # O nome do torrent continua na pasta antiga depois que o qBittorrent
        # já moveu o conteúdo para Título (Ano). Essa pasta ainda é do torrent.
        nome_torrent = (item.get("name") or "").strip()
        if (
            nome_torrent
            and "/" not in nome_torrent
            and "\\" not in nome_torrent
            and os.path.isdir(os.path.join(base, nome_torrent))
        ):
            nomes.append(nome_torrent)
        for nome in nomes:
            mapa[(base, nome)] = item
    return mapa


def listar_pastas_fora_padrao(biblioteca: dict, libraries: list[dict]) -> list[dict]:
    """Pastas imediatas da biblioteca cujo nome difere do alvo Título (Ano)."""
    if _demo():
        nome = (biblioteca.get("name") or "").lower()
        if "série" in nome or "serie" in nome:
            return [
                {
                    "atual": "From (2022) Season 1 S01 WEB-DL",
                    "alvo": "From (2022)",
                    "tem_torrent": False,
                    "hash": "",
                },
                {
                    "atual": "Silo (2023) Season 1 S01 1080p",
                    "alvo": "Silo (2023)",
                    "tem_torrent": False,
                    "hash": "",
                },
            ]
        return []
    caminho = biblioteca.get("path") or ""
    if not caminho or not os.path.isdir(caminho):
        return []
    base = os.path.realpath(caminho)
    torrents = _mapa_torrents_por_pasta(libraries)
    linhas: list[dict] = []
    try:
        entradas = os.listdir(caminho)
    except OSError:
        return []
    for nome in sorted(entradas):
        pasta = os.path.join(caminho, nome)
        if not os.path.isdir(pasta):
            continue
        alvo = alvo_da_pasta(nome)
        if alvo is None or nome == alvo:
            continue
        item = torrents.get((base, nome))
        hash_torrent = ""
        if item:
            hash_torrent = (item.get("hash") or "").lower()
            if not _HASH_RE.match(hash_torrent):
                hash_torrent = ""
        tem_torrent = bool(hash_torrent)
        linha = {
            "atual": nome,
            "alvo": alvo,
            "tem_torrent": tem_torrent,
            "hash": hash_torrent,
            "sem_ano": _sem_ano_pasta(nome),
            "aviso": _aviso_residuo_pasta(pasta, tem_torrent),
        }
        if tem_torrent and item:
            organizavel, feedback = _torrent_organizavel_e_feedback(item)
            linha["torrent_organizavel"] = organizavel
            linha["feedback"] = feedback
        linhas.append(linha)
    return linhas


def _renomear_pasta(hash_torrent: str, old_path: str, new_path: str) -> tuple[int, str]:
    return _abrir(
        "POST",
        "/api/v2/torrents/renameFolder",
        {"hash": hash_torrent, "oldPath": old_path, "newPath": new_path},
        timeout=60,
    )


def organizar_linhas(
    biblioteca: dict,
    nomes_marcados: list[str],
    libraries: list[dict],
    mesclar_pasta,
) -> dict:
    """Organiza só as pastas indicadas; pasta com torrent ativo fica em ignorados."""
    relatorio: dict = {"feitos": [], "nao_feitos": [], "ignorados": []}
    if _demo():
        marcados = [nome for nome in nomes_marcados if nome]
        if marcados:
            relatorio["feitos"].append(
                {"de": marcados[0], "para": alvo_da_pasta(marcados[0]) or marcados[0]}
            )
        if len(marcados) > 1:
            relatorio["nao_feitos"].append(
                {"nome": marcados[1], "motivo": "Demonstração: segunda linha não feita."}
            )
        return relatorio
    caminho = biblioteca.get("path") or ""
    if not caminho:
        raise AgentError("Biblioteca sem caminho")
    base = os.path.realpath(caminho)
    torrents = _mapa_torrents_por_pasta(libraries)
    vistos: set[str] = set()
    for bruto in nomes_marcados:
        atual = (bruto or "").strip()
        if not atual or atual in vistos:
            continue
        vistos.add(atual)
        pasta = os.path.join(caminho, atual)
        if not os.path.isdir(pasta):
            relatorio["nao_feitos"].append(
                {"nome": atual, "motivo": "Pasta não encontrada"}
            )
            continue
        alvo = alvo_da_pasta(atual)
        if alvo is None:
            relatorio["nao_feitos"].append({"nome": atual, "motivo": "Sem título"})
            continue
        if atual == alvo:
            relatorio["nao_feitos"].append({"nome": atual, "motivo": "Já no padrão"})
            continue
        item = torrents.get((base, atual))
        tem_torrent = bool(item)
        aviso = _aviso_residuo_pasta(pasta, tem_torrent)
        if _sem_ano_pasta(atual):
            entrada = {"nome": atual, "motivo": _SEM_ANO_MOTIVO}
            if aviso:
                entrada["aviso"] = aviso
            relatorio["nao_feitos"].append(entrada)
            continue
        if aviso:
            relatorio["nao_feitos"].append({"nome": atual, "motivo": aviso})
            continue
        if item:
            hash_torrent = (item.get("hash") or "").lower()
            if not _HASH_RE.match(hash_torrent):
                relatorio["nao_feitos"].append(
                    {"nome": atual, "motivo": "Torrent inválido"}
                )
                continue
            _organizavel, feedback = _torrent_organizavel_e_feedback(item)
            entrada = {"nome": atual, "motivo": feedback}
            if aviso:
                entrada["aviso"] = aviso
            relatorio["ignorados"].append(entrada)
            continue
        try:
            resultado = mesclar_pasta(biblioteca.get("id") or "", atual, alvo)
        except AgentError as exc:
            entrada = {"nome": atual, "motivo": str(exc)}
            if aviso:
                entrada["aviso"] = aviso
            relatorio["nao_feitos"].append(entrada)
            continue
        if not isinstance(resultado, dict):
            relatorio["nao_feitos"].append(
                {"nome": atual, "motivo": "Resposta inválida do agente"}
            )
            continue
        if resultado.get("ok"):
            feito = {"de": atual, "para": alvo}
            if aviso:
                feito["aviso"] = aviso
            relatorio["feitos"].append(feito)
        else:
            motivo = (resultado.get("motivo") or "").strip() or "Não foi possível organizar"
            entrada = {"nome": atual, "motivo": motivo}
            if aviso:
                entrada["aviso"] = aviso
            relatorio["nao_feitos"].append(entrada)
    return relatorio
