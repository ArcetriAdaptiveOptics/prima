#!/usr/bin/env bash
# Prima Drop 1 live GUI (Manta via Aravis; ModulatorClient if :7030 is up).
# Intended for x2go / desktop launcher — inherits session DISPLAY.
set -euo pipefail

VENV="${PRIMA_VENV:-$HOME/git/.venv-prima}"
if [[ ! -f "$VENV/bin/activate" ]]; then
  echo "Prima venv not found: $VENV" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$VENV/bin/activate"

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
# Prefer session display (x2go sets DISPLAY); do not hardcode :50.
if [[ -z "${DISPLAY:-}" ]]; then
  echo "DISPLAY is unset — start from a graphical session (e.g. x2go)." >&2
  exit 1
fi

ARAVIS_IP="${PRIMA_ARAVIS_IP:-192.168.30.189}"
exec prima-gui --live-aravis --aravis-ip "$ARAVIS_IP" "$@"
