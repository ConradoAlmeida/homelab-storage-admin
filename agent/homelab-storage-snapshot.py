#!/usr/bin/env python3
"""Cria um snapshot Btrfs para cada share com politica habilitada.

Roda como root no host e fala com o agente pelo Unix socket. E o alvo do
homelab-storage-snapshot.timer (diario). O app tambem permite snapshot manual.
"""
from __future__ import annotations

import json
import os
import socket
import sys

SOCKET_PATH = os.environ.get("AGENT_SOCKET", "/run/homelab-storage-admin/agent.sock")
TIMEOUT = int(os.environ.get("SNAPSHOT_TIMEOUT", "1800"))


def call(op: str, timeout: int = TIMEOUT, **payload):
    request = {"op": op, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(SOCKET_PATH)
        sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            if chunk.endswith(b"\n"):
                break
    raw = b"".join(chunks).strip()
    if not raw:
        raise RuntimeError("agente nao respondeu")
    response = json.loads(raw)
    if not response.get("ok"):
        raise RuntimeError(response.get("error", "erro desconhecido"))
    return response.get("data")


def main() -> int:
    try:
        policies = call("snapshot_usage", timeout=120)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERRO: nao foi possivel consultar o agente: {exc}", file=sys.stderr)
        return 1

    enabled = [p for p in policies if p.get("enabled")]
    if not enabled:
        print("Nenhuma politica de snapshot habilitada.")
        return 0

    failures = 0
    for policy in enabled:
        share = policy["share"]
        try:
            result = call("snapshot_create", share=share)
            print(f"{share}: {result.get('name')}")
        except (OSError, RuntimeError, json.JSONDecodeError) as exc:
            failures += 1
            print(f"ERRO em {share}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
