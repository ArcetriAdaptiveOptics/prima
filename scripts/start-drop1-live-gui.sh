#!/usr/bin/env bash
# Prima Drop 1 live GUI launcher (desktop / Applications / x2go).
#
# - Sources ~/git/.venv-prima and inherits the session DISPLAY (do not hardcode).
# - Starts: prima-gui --live-aravis --aravis-ip 192.168.30.189  (Manta G-419)
#
# Lab modulator (PI S-334 @ E-518 via plico_dm_server :7030):
#   In the GUI, use profile "lab" → Start → Connect live when the modulator
#   server can load. Real E-518 still needs the PI GCS2 shared library
#   (libpi_pi_gcs2.so from the PI E-518 SDK) on this laptop — until that .so
#   is installed, Start lab will fail to keep the modulator server up even
#   though the controller may answer *IDN? on 192.168.30.190:50000.
#   Camera live Aravis works without GCS2.
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
