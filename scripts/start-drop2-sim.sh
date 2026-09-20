#!/usr/bin/env bash
# Drop 2 sim stack: camera + modulator + BMC DM (all sim confs).
# Usage: ./scripts/start-drop2-sim.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

CAM_CONF="$ROOT/conf/camera-sim.conf"
MOD_CONF="$ROOT/conf/modulator-sim.conf"
DM_CONF="$ROOT/conf/dm-bmc-sim.conf"

echo "Camera:    $CAM_CONF"
echo "Modulator: $MOD_CONF"
echo "DM:        $DM_CONF"

pysilico_server "$CAM_CONF" camera1 &
CAM_PID=$!
plico_dm_server "$MOD_CONF" modulator1 &
MOD_PID=$!
plico_dm_server "$DM_CONF" dmBmc &
DM_PID=$!

echo "PIDs camera=$CAM_PID modulator=$MOD_PID dm=$DM_PID"
echo "GUIs:"
echo "  prima-gui"
echo "  prima-dm-gui [--live]"
echo "  daoprima-gui"
echo "Stop: kill $CAM_PID $MOD_PID $DM_PID"
wait
