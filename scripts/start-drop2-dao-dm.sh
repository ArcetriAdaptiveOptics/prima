#!/usr/bin/env bash
# Start Drop 2 DM GUI (DAO SHM). Optionally start daodm_bmc_ctrl.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "${HOME}/git/.venv-prima/bin/activate"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"
PREFER="${1:-auto}"
python -m daoprima.apps.daodm_bmc_ctrl --prefer "$PREFER" --create-graph &
CTRL_PID=$!
trap 'kill $CTRL_PID 2>/dev/null || true' EXIT
sleep 0.4
exec python -m prima.gui.dm_panel --prefer "$PREFER"
