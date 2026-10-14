#!/usr/bin/env bash
# Drop 2a — start simulated BMC Multi-DM (140 act) via plico_dm_server.
# Usage: ./scripts/start-drop2-dm-sim.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF="$ROOT/conf/dm-bmc-sim.conf"
echo "BMC DM conf: $CONF"
plico_dm_server "$CONF" dmBmc &
DM_PID=$!
echo "Started dmBmc PID=$DM_PID  (port 7050)"
echo "Stop with: kill $DM_PID"
echo
echo "Smoke:"
echo "  python -c \"import plico_dm, numpy as np, time; time.sleep(1); dm=plico_dm.deformableMirror('localhost',7050); print(dm.getNumberOfActuators()); dm.setShape(np.zeros(140)); print('shape_ok')\""
wait
