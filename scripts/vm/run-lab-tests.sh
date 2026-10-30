#!/usr/bin/env bash
# Roda os testes de laboratorio (loop devices, mdadm, Btrfs, restic e grupos)
# na VM. Exige root.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERRO: rode com sudo: sudo bash scripts/vm/run-lab-tests.sh" >&2
    exit 1
fi

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOMELAB_LAB=1 /usr/local/bin/uv run --python 3.12 pytest tests/lab -q
