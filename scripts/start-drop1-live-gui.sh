#!/usr/bin/env bash
# Prima Drop 1 live GUI — Aravis Manta + direct PI E-518 GCS (no plico servers).
set -euo pipefail

VENV="${PRIMA_VENV:-$HOME/git/.venv-prima}"
# shellcheck source=/dev/null
source "$VENV/bin/activate"

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
if [[ -z "${DISPLAY:-}" ]]; then
  echo "DISPLAY is unset — start from a graphical session (e.g. x2go)." >&2
  exit 1
fi

ARAVIS_IP="${PRIMA_ARAVIS_IP:-192.168.30.189}"
E518_HOST="${PRIMA_E518_HOST:-192.168.30.190}"
E518_PORT="${PRIMA_E518_PORT:-50000}"

exec prima-gui --live \
  --aravis-ip "$ARAVIS_IP" \
  --e518-host "$E518_HOST" \
  --e518-port "$E518_PORT" \
  "$@"
