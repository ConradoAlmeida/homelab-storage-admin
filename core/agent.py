import json
import socket

from django.conf import settings


class AgentError(Exception):
    pass


class AgentClient:
    """Cliente do agente privilegiado que roda no host (Unix socket)."""

    def __init__(self, socket_path: str | None = None, timeout: int | None = None):
        self.socket_path = socket_path or settings.AGENT_SOCKET
        self.timeout = timeout or settings.AGENT_TIMEOUT

    def call(self, op: str, timeout: int | None = None, **payload):
        if not hasattr(socket, "AF_UNIX"):
            raise AgentError(
                "Unix socket nao suportado nesta plataforma. Rode o app no Linux/servidor."
            )
        request = {"op": op, **payload}
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout or self.timeout)
                sock.connect(self.socket_path)
                sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
                chunks = []
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if chunk.endswith(b"\n"):
                        break
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            raise AgentError(
                f"Nao foi possivel falar com o agente em {self.socket_path}: {exc}"
            ) from exc

        raw = b"".join(chunks).strip()
        if not raw:
            raise AgentError("Agente nao respondeu")
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError(f"Resposta invalida do agente: {raw[:200]!r}") from exc

        if not response.get("ok"):
            raise AgentError(response.get("error", "Erro desconhecido no agente"))
        return response.get("data")

    # atalhos
    def ping(self):
        return self.call("ping")

    def host_capabilities(self):
        return self.call("host_capabilities", timeout=20)

    def df(self):
        return self.call("df")

    def list_users(self):
        return self.call("list_users")

    def list_groups(self):
        return self.call("list_groups")

    def create_group(self, name, gid=None):
        return self.call("create_group", name=name, gid=gid)

    def create_user(self, username, password, groups=None):
        return self.call("create_user", username=username, password=password, groups=groups or [])

    def set_password(self, username, password):
        return self.call("set_password", username=username, password=password)

    def set_groups(self, username, groups):
        return self.call("set_groups", username=username, groups=groups)

    def toggle_user(self, username, enabled):
        return self.call("toggle_user", username=username, enabled=enabled)

    def list_shares(self, include_size=False):
        timeout = 180 if include_size else None
        return self.call("list_shares", timeout=timeout, include_size=include_size)

    def create_share(self, name, path, comment="", snapshot=False, snapshot_keep=7, private=False):
        return self.call(
            "create_share",
            name=name,
            path=path,
            comment=comment,
            snapshot=snapshot,
            snapshot_keep=snapshot_keep,
            private=private,
        )

    def snapshot_usage(self, include_size=True):
        timeout = 180 if include_size else None
        return self.call("snapshot_usage", timeout=timeout, include_size=include_size)

    def snapshot_list(self, share):
        return self.call("snapshot_list", share=share)

    def snapshot_create(self, share):
        # btrfs snapshot pode demorar; usa timeout proprio sem enviar ao agente
        return self.call("snapshot_create", timeout=1800, share=share)

    def snapshot_delete(self, share, name):
        return self.call("snapshot_delete", share=share, name=name)

    def storage_overview(self):
        # hdparm/smartctl podem demorar alguns segundos por disco
        return self.call("storage_overview", timeout=90)

    def storage_smart(self, device):
        return self.call("storage_smart", timeout=60, device=device)

    def storage_smart_test(self, device, kind="short"):
        return self.call("storage_smart_test", timeout=90, device=device, kind=kind)

    def backup_overview(self):
        return self.call("backup_overview", timeout=60)

    def backup_disk_setup(self, device, label, confirmation, allow_existing=False):
        return self.call(
            "backup_disk_setup",
            timeout=900,
            device=device,
            label=label,
            confirmation=confirmation,
            allow_existing=allow_existing,
        )

    def backup_secret(self, uuid):
        return self.call("backup_secret", timeout=30, uuid=uuid)

    def backup_job_save(self, job):
        return self.call("backup_job_save", timeout=60, job=job)

    def backup_job_toggle(self, name, enabled):
        return self.call("backup_job_toggle", timeout=60, name=name, enabled=enabled)

    def backup_job_delete(self, name):
        return self.call("backup_job_delete", timeout=60, name=name)

    def backup_job_run(self, name):
        return self.call("backup_job_run", timeout=30, name=name)

    def cold_overview(self):
        return self.call("cold_overview", timeout=60)

    def cold_prepare(self, device, label, confirmation, allow_existing=False):
        return self.call(
            "cold_prepare",
            timeout=900,
            device=device,
            label=label,
            confirmation=confirmation,
            allow_existing=allow_existing,
        )

    def cold_copy(self):
        return self.call("cold_copy", timeout=3900)

    def cold_eject(self):
        return self.call("cold_eject", timeout=60)

    def network_metrics(self):
        return self.call("network_metrics", timeout=15)


agent = AgentClient()
