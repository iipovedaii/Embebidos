#!/usr/bin/env bash
# Crea/usa .venv del proyecto (Arch Linux PEP 668) e instala deps del broker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Creando entorno virtual en .venv ..."
  python3 -m venv "$ROOT/.venv"
fi

"$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements-broker.txt"
echo "$ROOT/.venv/bin/python"
