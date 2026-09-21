#!/usr/bin/env bash
# Start stock pysilico_server for Drop1 Manta via Vimba X (vmbpy).
set -euo pipefail
source "${PRIMA_VENV:-$HOME/git/.venv-prima}/bin/activate"

VIMBAX_CTI="${PRIMA_VIMBAX_CTI:-$HOME/git/vendor-sdks/VimbaX_2025-2/cti}"
export GENICAM_GENTL64_PATH="$VIMBAX_CTI${GENICAM_GENTL64_PATH:+:$GENICAM_GENTL64_PATH}"
export LD_LIBRARY_PATH="$(dirname "$VIMBAX_CTI")/api/lib:$(dirname "$VIMBAX_CTI")/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

ROOT="${PRIMA_ROOT:-$HOME/git/prima}"
LOGDIR="$ROOT/tmp/gui-logs"
CONF="$ROOT/conf/camera-manta-g419.conf"
mkdir -p "$LOGDIR"

if [[ -f $LOGDIR/camera.pid ]]; then
  old=$(cat "$LOGDIR/camera.pid" || true)
  if [[ -n "${old:-}" ]] && kill -0 "$old" 2>/dev/null; then
    kill "$old" || true
    sleep 1
    kill -9 "$old" 2>/dev/null || true
  fi
fi
fuser -k 7130/tcp 7131/tcp 7132/tcp 7133/tcp 2>/dev/null || true
sleep 1

: > "$LOGDIR/camera.out"
cd "$ROOT"
nohup pysilico_server "$CONF" camera1 >>"$LOGDIR/camera.out" 2>&1 &
echo $! > "$LOGDIR/camera.pid"
echo "started pid=$(cat "$LOGDIR/camera.pid") GENICAM=$GENICAM_GENTL64_PATH"

# Wait until status answers or fail
python - <<'PY'
import os, time, sys
sys.path.insert(0, '')
import pysilico
from plico.rpc.zmq_remote_procedure_call import ZmqRpcTimeoutError
deadline = time.time() + 25
last = None
while time.time() < deadline:
    try:
        c = pysilico.camera('localhost', 7130)
        st = c.getStatus()
        print('READY name=%s shape=%s' % (getattr(st, 'name', '?'), c.shape()))
        sys.exit(0)
    except Exception as e:
        last = e
        time.sleep(0.5)
print('NOT_READY:', type(last).__name__, last)
sys.exit(2)
PY
