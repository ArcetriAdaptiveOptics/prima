#!/usr/bin/env bash
# Start Prima phase-1 device plane: WFS camera + PWFS modulator (sim by default).
# Usage:
#   ./scripts/start-phase1-sim.sh
#   PROFILE=lab ./scripts/start-phase1-sim.sh   # Manta + E-518 (needs hardware + Vimba)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-sim}"

if [[ "$PROFILE" == "lab" ]]; then
  CAM_CONF="$ROOT/conf/camera-manta-g419.conf"
  MOD_CONF="$ROOT/conf/modulator-lab-e518.conf"
else
  CAM_CONF="$ROOT/conf/camera-sim.conf"
  MOD_CONF="$ROOT/conf/modulator-sim.conf"
fi

echo "Camera conf:    $CAM_CONF"
echo "Modulator conf: $MOD_CONF"

pysilico_server "$CAM_CONF" camera1 &
CAM_PID=$!
plico_dm_server "$MOD_CONF" modulator1 &
MOD_PID=$!

echo "Started camera PID=$CAM_PID  modulator PID=$MOD_PID"
echo "Stop with: kill $CAM_PID $MOD_PID"
echo
echo "Smoke (modulator):"
echo "  python -c \"import plico_dm, time; time.sleep(1); m=plico_dm.modulator('localhost',7030); m.setRadiusInMilliRad(1.5); m.setFrequencyInHz(20); print(m.getStatus())\""
wait
