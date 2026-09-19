"""Start/stop helpers for Drop 1 plico processes (sim or lab conf)."""
import os
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ProcessManager:
    def __init__(self, profile='sim', root=None):
        self.root = Path(root) if root else ROOT
        self.profile = profile
        self._procs = {}
        self._log_handles = []

    def _confs(self):
        if self.profile == 'lab':
            return (
                self.root / 'conf' / 'camera-manta-g419.conf',
                self.root / 'conf' / 'modulator-lab-e518.conf',
            )
        return (
            self.root / 'conf' / 'camera-sim.conf',
            self.root / 'conf' / 'modulator-sim.conf',
        )

    def status(self):
        out = {}
        for name, proc in self._procs.items():
            out[name] = {
                'pid': proc.pid if proc else None,
                'running': proc is not None and proc.poll() is None,
            }
        return out

    def start(self):
        cam_conf, mod_conf = self._confs()
        log_dir = self.root / 'tmp' / 'gui-logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        self.stop()
        env = os.environ.copy()
        cam_log = open(log_dir / 'camera.out', 'ab')
        mod_log = open(log_dir / 'modulator.out', 'ab')
        self._log_handles = [cam_log, mod_log]
        self._procs['camera'] = subprocess.Popen(
            ['pysilico_server', str(cam_conf), 'camera1'],
            stdout=cam_log, stderr=subprocess.STDOUT, env=env)
        self._procs['modulator'] = subprocess.Popen(
            ['plico_dm_server', str(mod_conf), 'modulator1'],
            stdout=mod_log, stderr=subprocess.STDOUT, env=env)
        time.sleep(0.5)
        return self.status()

    def stop(self):
        for name, proc in list(self._procs.items()):
            if proc is None:
                continue
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            self._procs[name] = None
        for h in self._log_handles:
            try:
                h.close()
            except Exception:
                pass
        self._log_handles = []
        return self.status()
