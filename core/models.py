from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=80)
    target = models.CharField(max_length=160, blank=True)
    detail = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}"


class TorrentApiToken(models.Model):
    """Token legível da API de torrents. Uma linha, criada na primeira consulta."""

    token = models.TextField(blank=True)

    def __str__(self) -> str:
        return "Token da API de torrents"


def token_da_api() -> str:
    """Valor em uso. O host.env só preenche a linha quando ela ainda não existe."""
    registro, _criado = TorrentApiToken.objects.get_or_create(
        pk=1,
        defaults={"token": settings.TORRENT_API_TOKEN or ""},
    )
    return registro.token or ""


def definir_token_da_api(valor: str) -> None:
    TorrentApiToken.objects.update_or_create(pk=1, defaults={"token": valor})
