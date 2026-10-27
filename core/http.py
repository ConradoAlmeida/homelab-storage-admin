from __future__ import annotations

import mimetypes
from pathlib import Path

from django.http import FileResponse, JsonResponse

from .agent import AgentError


def file_response(path: Path, filename: str | None = None) -> FileResponse:
    """Resposta de download comum, sem expor o caminho do host."""
    name = filename or path.name
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    response = FileResponse(
        open(path, "rb"),
        as_attachment=True,
        filename=name,
        content_type=content_type,
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


def agent_json_error(exc: AgentError, status: int = 503) -> JsonResponse:
    return JsonResponse({"error": str(exc)}, status=status)
