"""Start/stop helpers for Drop 1 / Drop 2 plico processes (sim or lab conf)."""
import os
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProcessManager:
    def __init__(self, profile='sim', root=None, include_dm=False):
        self.root = Path(root) if root else ROOT
        self.profile = profile
        self.include_dm = include_dm
        self._procs = {}
        self._log_handles = []

    def _confs(self):
        if self.profile == 'lab':
            cam = self.root / 'conf' / 'camera-manta-g419.conf'
            mod = self.root / 'conf' / 'modulator-lab-e518.conf'
            dm = self.root / 'conf' / 'dm-bmc-lab.conf'
        elif self.profile == 'alvium':
            cam = self.root / 'conf' / 'camera-alvium-g1.conf'
            mod = self.root / 'conf' / 'modulator-lab-e518.conf'
            dm = self.root / 'conf' / 'dm-bmc-lab.conf'
        else:
            cam = self.root / 'conf' / 'camera-sim.conf'
            mod = self.root / 'conf' / 'modulator-sim.conf'
            dm = self.root / 'conf' / 'dm-bmc-sim.conf'
        return cam, mod, dm

    def status(self):
        out = {}
        for name, proc in self._procs.items():
            out[name] = {
                'pid': proc.pid if proc else None,
                'running': proc is not None and proc.poll() is None,
            }
        return out

    def start(self):
        cam_conf, mod_conf, dm_conf = self._confs()
        log_dir = self.root / 'tmp' / 'gui-logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        self.stop()
        env = os.environ.copy()
        # Vimba X GenTL for stock pysilico avt (Manta)
        cti = os.environ.get(
            'PRIMA_VIMBAX_CTI',
            os.path.expanduser('~/git/vendor-sdks/VimbaX_2025-2/cti'))
        if os.path.isdir(cti):
            prev = env.get('GENICAM_GENTL64_PATH', '')
            parts = [p for p in prev.split(':') if p and p != cti]
            env['GENICAM_GENTL64_PATH'] = ':'.join([cti] + parts)
            api = os.path.abspath(os.path.join(cti, '..', 'api', 'lib'))
            bindir = os.path.abspath(os.path.join(cti, '..', 'bin'))
            ld = [p for p in env.get('LD_LIBRARY_PATH', '').split(':') if p]
            for p in (api, bindir):
                if p not in ld:
                    ld.insert(0, p)
            env['LD_LIBRARY_PATH'] = ':'.join(ld)
        cam_log = open(log_dir / 'camera.out', 'ab')
        mod_log = open(log_dir / 'modulator.out', 'ab')
        self._log_handles = [cam_log, mod_log]
        self._procs['camera'] = subprocess.Popen(
            ['pysilico_server', str(cam_conf), 'camera1'],
            stdout=cam_log, stderr=subprocess.STDOUT, env=env,
            start_new_session=True)
        # Lab modulator via plico is deferred; still spawn sim profile only.
        if self.profile == 'sim':
            self._procs['modulator'] = subprocess.Popen(
                ['plico_dm_server', str(mod_conf), 'modulator1'],
                stdout=mod_log, stderr=subprocess.STDOUT, env=env,
                start_new_session=True)
        else:
            # Lab: Drop1 uses direct GCS TCP — do not start plico_dm_server.
            self._procs['modulator'] = None
            mod_log.write(
                b'(skipped) lab modulator uses direct PI GCS TCP, not plico_dm\n')
            mod_log.flush()
        if self.include_dm:
            dm_log = open(log_dir / 'dm.out', 'ab')
            self._log_handles.append(dm_log)
            self._procs['dm'] = subprocess.Popen(
                ['plico_dm_server', str(dm_conf), 'dmBmc'],
                stdout=dm_log, stderr=subprocess.STDOUT, env=env,
                start_new_session=True)
        time.sleep(2.5 if self.profile in ('lab', 'alvium') else 0.5)
        st = self.status()
        # Surface early exits (e.g. missing Vimba) in status.
        for name, proc in self._procs.items():
            if proc is None:
                st[name] = {'pid': None, 'running': False, 'skipped': True}
                continue
            if proc.poll() is not None:
                st[name]['running'] = False
                st[name]['exit_code'] = proc.returncode
                log_path = log_dir / ('%s.out' % name)
                try:
                    tail = log_path.read_text(errors='replace')[-800:]
                except Exception:
                    tail = ''
                st[name]['log_tail'] = tail
        return st

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
