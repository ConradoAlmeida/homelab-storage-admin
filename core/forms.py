from django import forms
from django.conf import settings


class UserCreateForm(forms.Form):
    username = forms.RegexField(
        regex=r"^[a-z][a-z0-9._-]{2,31}$",
        label="Usuario",
        help_text="minusculas, 3-32 caracteres (a-z, 0-9, . _ -)",
    )
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput,
        min_length=8,
        help_text="Minimo 8 caracteres. Senha do Samba: a conta Linux nao recebe senha.",
    )
    groups = forms.MultipleChoiceField(
        label="Grupos",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, group_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].choices = [(g, g) for g in (group_choices or [])]


class GroupCreateForm(forms.Form):
    name = forms.RegexField(
        regex=r"^[a-z][a-z0-9._-]{1,31}$",
        label="Nome do grupo",
        help_text="minusculas, 2-32 caracteres (a-z, 0-9, . _ -)",
    )
    gid = forms.IntegerField(
        label="GID",
        min_value=1000,
        max_value=60000,
        required=False,
        help_text="Opcional. Se vazio, o sistema escolhe um GID livre >= 1000.",
    )


class PasswordForm(forms.Form):
    username = forms.CharField(widget=forms.HiddenInput)
    password = forms.CharField(label="Nova senha", widget=forms.PasswordInput, min_length=8)


class GroupsForm(forms.Form):
    username = forms.CharField(widget=forms.HiddenInput)
    groups = forms.MultipleChoiceField(
        label="Grupos", required=False, widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, group_choices=None, initial_groups=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].choices = [(g, g) for g in (group_choices or [])]
        if initial_groups:
            self.initial["groups"] = initial_groups


class TorrentAddForm(forms.Form):
    magnet = forms.CharField(
        label="Link magnético",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Somente magnet:?xt=urn:btih:.... Endereços http não são aceitos.",
    )
    library = forms.ChoiceField(
        label="Pasta do Jellyfin",
        help_text="O torrent entra numa das bibliotecas já configuradas no Jellyfin.",
    )

    def __init__(self, *args, libraries=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["library"].choices = [
            (item["id"], f"{item['name']} — {item['path']}") for item in (libraries or [])
        ]

    def clean_magnet(self):
        valor = "".join(self.cleaned_data["magnet"].split())
        if len(valor) > 4096 or not valor.lower().startswith("magnet:?"):
            raise forms.ValidationError("Use um link magnet:?xt=urn:btih:...")
        if "xt=urn:btih:" not in valor.lower():
            raise forms.ValidationError("O link precisa ter xt=urn:btih:.")
        return valor


class SnapshotPolicyForm(forms.Form):
    share = forms.ChoiceField(
        label="Share",
        help_text="Somente shares que ainda não têm política.",
    )
    keep = forms.IntegerField(
        label="Versões a manter",
        min_value=1,
        max_value=168,
        initial=7,
        help_text="Reduzir o número só apaga versões antigas no próximo snapshot.",
    )
    enabled = forms.BooleanField(
        label="Política ativa",
        required=False,
        initial=True,
        help_text="Desativar impede novos snapshots. Os que já existem permanecem no disco.",
    )
    create_now = forms.BooleanField(
        label="Criar um snapshot agora",
        required=False,
        initial=False,
        help_text="Gera a primeira versão assim que a política for salva.",
    )

    def __init__(
        self,
        *args,
        share_choices=None,
        lock_share=None,
        show_create_now=True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        if lock_share:
            self.fields["share"] = forms.CharField(
                widget=forms.HiddenInput, initial=lock_share
            )
        else:
            self.fields["share"].choices = share_choices or []
        if not show_create_now:
            del self.fields["create_now"]


class ShareCreateForm(forms.Form):
    name = forms.RegexField(
        regex=r"^[A-Za-z0-9_-]{1,32}$",
        label="Nome do share",
        help_text="1-32 caracteres (A-Z, a-z, 0-9, _ -)",
    )
    path = forms.CharField(
        label="Caminho",
        max_length=255,
        help_text="",
    )
    comment = forms.CharField(label="Descricao", required=False)
    snapshot = forms.BooleanField(
        label="Criar com snapshot e incluir na politica de versoes",
        required=False,
        initial=False,
        help_text="Btrfs usa subvolume; ext4 usa snapshots rsync com hardlinks.",
    )
    snapshot_keep = forms.IntegerField(
        label="Versoes a manter", min_value=1, max_value=168, initial=7, required=False
    )
    private = forms.BooleanField(
        label="Privado (oculto na rede)",
        required=False,
        initial=False,
        help_text="Adiciona browseable = no; o acesso continua restrito pelos grupos <share>_ro/_rw.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        prefixes = settings.ALLOWED_PATH_PREFIXES
        if prefixes:
            self.fields["path"].help_text = f"Ex.: {prefixes[0]}documentos"

    def clean_path(self):
        path = self.cleaned_data["path"].strip().rstrip("/")
        if not path.startswith("/"):
            raise forms.ValidationError("Use caminho absoluto.")
        if ".." in path.split("/"):
            raise forms.ValidationError("Caminho invalido.")
        prefixes = settings.ALLOWED_PATH_PREFIXES
        if not prefixes:
            raise forms.ValidationError("Nenhum caminho permitido configurado.")
        if not path.startswith(prefixes):
            raise forms.ValidationError(
                "Use um caminho permitido: " + ", ".join(prefixes)
            )
        return path
