#!/usr/bin/env bash
# PRIMA AO lab GUI on the real bench, course configuration (41 Hz loop):
# decimation 2, t_exp 20 ms = 1 modulation period at 50 Hz, camera gain 6 dB.
# Extra arguments are passed to the GUI (e.g. --sim for the numerical twin).
set -euo pipefail

VENV="${PRIMA_VENV:-$HOME/git/.venv-prima}"
# shellcheck source=/dev/null
source "$VENV/bin/activate"
cd "$HOME/git/prima"

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
if [[ -z "${DISPLAY:-}" ]]; then
  echo "DISPLAY is unset — start from a graphical session." >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  set -- --hw --binning 2 --exposure 20 --fmod 50 --cam-gain 6
fi
python -m prima.aolab.gui "$@" && status=0 || status=$?
echo
echo "GUI exited with status $status. Press Enter to close this window."
read -r _
