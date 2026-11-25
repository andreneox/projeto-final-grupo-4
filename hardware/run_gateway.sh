#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${1:-$ROOT/config.toml}"
exec "$ROOT/.venv/bin/python" "$ROOT/main.py" --config "$CONFIG"

