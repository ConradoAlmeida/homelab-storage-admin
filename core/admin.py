from django import forms
from django.contrib import admin

from .downloads import _token_aceitavel
from .models import AuditLog, TorrentApiToken


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target")
    list_filter = ("action",)
    readonly_fields = ("created_at",)


class TorrentApiTokenForm(forms.ModelForm):
    class Meta:
        model = TorrentApiToken
        fields = ("token",)
        widgets = {
            "token": forms.TextInput(
                attrs={"autocomplete": "off", "spellcheck": "false"}
            )
        }
        help_texts = {
            "token": "De 16 a 256 caracteres, sem espaços. Vazio desliga a API.",
        }

    def clean_token(self):
        valor = self.cleaned_data.get("token") or ""
        if valor and not _token_aceitavel(valor):
            raise forms.ValidationError(
                "O token precisa ter de 16 a 256 caracteres, sem espaços."
            )
        return valor


@admin.register(TorrentApiToken)
class TorrentApiTokenAdmin(admin.ModelAdmin):
    form = TorrentApiTokenForm
    list_display = ("__str__", "definido")

    @admin.display(description="Definido", boolean=True)
    def definido(self, obj):
        return bool(obj.token)

    def has_add_permission(self, request):
        return not TorrentApiToken.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.pk = 1
        obj.token = form.cleaned_data.get("token") or ""
        obj.save()
