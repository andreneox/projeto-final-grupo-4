#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Execute como root: sudo bash deploy/install.sh <servidor> <porta-serial> [gateway-id]" >&2
    exit 1
fi

if [[ "$#" -lt 2 || "$#" -gt 3 ]]; then
    echo "Uso: sudo bash deploy/install.sh <servidor> <porta-serial> [gateway-id]" >&2
    echo "Exemplo: sudo bash deploy/install.sh 192.168.1.10 /dev/serial/by-id/usb-FTDI_FT232R-if00-port0 LINHA_A" >&2
    exit 1
fi

SERVER_ADDRESS="$1"
SERIAL_PORT="$2"
GATEWAY_ID="${3:-LINHA_A}"
SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="/opt/lean-gateway"
CONFIG_DIR="/etc/lean-gateway"
CONFIG_PATH="$CONFIG_DIR/config.toml"
DATA_DIR="/var/lib/lean-gateway"
LOG_DIR="/var/log/lean-gateway"

for required in python3 systemctl; do
    if ! command -v "$required" >/dev/null 2>&1; then
        echo "Comando obrigatorio ausente: $required" >&2
        exit 1
    fi
done

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Instale python3-venv antes de continuar." >&2
    exit 1
fi

if ! id gateway >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin gateway
fi
usermod -aG dialout gateway

systemctl stop gateway.service 2>/dev/null || true

install -d -o root -g root -m 0755 "$APP_DIR"
install -d -o root -g dialout -m 0750 "$CONFIG_DIR"
install -d -o gateway -g dialout -m 0750 "$DATA_DIR" "$LOG_DIR"

if [[ "$SOURCE_ROOT" != "$APP_DIR" ]]; then
    rm -rf "$APP_DIR/gateway" "$APP_DIR/tools"
    cp -a "$SOURCE_ROOT/gateway" "$APP_DIR/gateway"
    cp -a "$SOURCE_ROOT/tools" "$APP_DIR/tools"
    install -m 0644 "$SOURCE_ROOT/main.py" "$APP_DIR/main.py"
    install -m 0644 "$SOURCE_ROOT/requirements.txt" "$APP_DIR/requirements.txt"
    install -m 0644 "$SOURCE_ROOT/README.md" "$APP_DIR/README.md"
fi

if [[ ! -d "$APP_DIR/.venv" ]]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

rm -rf "$CONFIG_DIR/certificates"
cp -a "$SOURCE_ROOT/certificates" "$CONFIG_DIR/certificates"
chown -R root:dialout "$CONFIG_DIR/certificates"
find "$CONFIG_DIR/certificates" -type d -exec chmod 0750 {} \;
find "$CONFIG_DIR/certificates" -type f -exec chmod 0640 {} \;

if [[ ! -f "$CONFIG_PATH" ]]; then
    python3 - "$SOURCE_ROOT/deploy/config.raspberry.toml" "$CONFIG_PATH" \
        "$SERVER_ADDRESS" "$SERIAL_PORT" "$GATEWAY_ID" <<'PY'
from pathlib import Path
import sys

template_path, output_path, server, serial_port, gateway_id = sys.argv[1:]
text = Path(template_path).read_text(encoding="utf-8")
values = {
    "__SERVER_ADDRESS__": server,
    "__SERIAL_PORT__": serial_port,
    "__GATEWAY_ID__": gateway_id,
}
for marker, value in values.items():
    if '"' in value or "\n" in value or "\r" in value:
        raise SystemExit(f"Valor invalido para {marker}: {value!r}")
    text = text.replace(marker, value)
Path(output_path).write_text(text, encoding="utf-8")
PY
else
    echo "Configuracao existente preservada: $CONFIG_PATH"
fi
chown root:dialout "$CONFIG_PATH"
chmod 0640 "$CONFIG_PATH"

chown -R root:root "$APP_DIR/gateway" "$APP_DIR/tools"
chown root:root "$APP_DIR/main.py" "$APP_DIR/requirements.txt" "$APP_DIR/README.md"
install -m 0644 "$SOURCE_ROOT/deploy/gateway.service" /etc/systemd/system/gateway.service

systemctl daemon-reload
if systemctl cat pigpiod.service >/dev/null 2>&1; then
    systemctl enable --now pigpiod.service
elif ! pgrep -x pigpiod >/dev/null 2>&1; then
    echo "AVISO: pigpiod nao esta ativo. Inicie sua configuracao do pigpio antes de testar o motor." >&2
fi

systemctl enable --now gateway.service

echo
echo "Gateway instalado e iniciado."
echo "Configuracao: $CONFIG_PATH"
echo "Status: sudo systemctl status gateway --no-pager"
echo "Logs:   sudo journalctl -u gateway -f"
