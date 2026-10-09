#!/usr/bin/env python3
"""PRIMA lab runner — lets a remote Claude session run jobs on this laptop.

Started BY HAND by the operator in a terminal on the alienware:

    python3 ~/git/prima/tools/labrunner.py

It polls ``~/git/prima/work/runner/queue/`` for ``*.json`` job files, runs
each one, and writes ``out/<id>.log`` + ``out/<id>.result.json``.  Every
command is echoed in this terminal.  Stop with Ctrl-C, or by creating the
file ``work/runner/STOP``.

Job file format::

    {"id": "20261009-1700-status",
     "cmd": ["git", "status"],          # list (no shell) or string (bash -lc)
     "cwd": "~/git/prima",              # optional, default ~/git/prima
     "timeout": 600,                    # optional seconds, default 600
     "venv": true}                      # optional: activate ~/git/.venv-prima

Hard rules enforced here (independent of what the job says):
  * never runs as root, never uses sudo;
  * refuses any job mentioning the other bench plug (mss425e);
  * one job at a time, with a timeout.
Only Python stdlib is used.
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
REPO = HOME / 'git' / 'prima'
BASE = REPO / 'work' / 'runner'
QUEUE = BASE / 'queue'
DONE = BASE / 'done'
OUT = BASE / 'out'
STOP = BASE / 'STOP'
VENV = HOME / 'git' / '.venv-prima'
FORBIDDEN = ('mss425e', 'sudo ', 'sudo\t', ' rm -rf /', 'mkfs', 'dd if=')
POLL_S = 1.0


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _env(use_venv: bool) -> dict:
    env = dict(os.environ)
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    env['PRIMA_LABRUNNER'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    if use_venv and VENV.exists():
        env['VIRTUAL_ENV'] = str(VENV)
        env['PATH'] = str(VENV / 'bin') + os.pathsep + env.get('PATH', '')
    return env


def run_job(path: Path) -> None:
    try:
        job = json.loads(path.read_text())
    except Exception as exc:  # malformed: move aside
        print('[%s] bad job %s: %s' % (_now(), path.name, exc))
        path.rename(DONE / (path.name + '.bad'))
        return
    jid = str(job.get('id') or path.stem)
    cmd = job.get('cmd')
    text = json.dumps(cmd)
    log = OUT / ('%s.log' % jid)
    res = OUT / ('%s.result.json' % jid)
    result = {'id': jid, 'cmd': cmd, 'start': _now()}
    if any(f in text.lower() for f in FORBIDDEN):
        result.update(returncode=-999, error='refused: forbidden token')
        res.write_text(json.dumps(result, indent=1))
        path.rename(DONE / path.name)
        print('[%s] REFUSED %s %s' % (_now(), jid, text))
        return
    cwd = Path(os.path.expanduser(job.get('cwd', str(REPO))))
    timeout = float(job.get('timeout', 600))
    if isinstance(cmd, str):
        argv = ['bash', '-c', cmd]
    else:
        argv = [str(c) for c in cmd]
    print('[%s] RUN %s  (cwd=%s, timeout=%ss)\n    %s'
          % (_now(), jid, cwd, int(timeout),
             cmd if isinstance(cmd, str) else shlex.join(argv)))
    t0 = time.time()
    with open(log, 'w') as fh:
        fh.write('# job %s  %s\n# cmd: %s\n\n' % (jid, _now(), text))
        fh.flush()
        try:
            p = subprocess.Popen(argv, cwd=str(cwd), stdout=fh,
                                 stderr=subprocess.STDOUT,
                                 env=_env(bool(job.get('venv', True))),
                                 start_new_session=True)
            try:
                rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGTERM)
                time.sleep(2)
                if p.poll() is None:
                    os.killpg(p.pid, signal.SIGKILL)
                rc = -9
                fh.write('\n# TIMEOUT after %ss\n' % timeout)
        except Exception as exc:
            rc = -1
            fh.write('\n# runner exception: %r\n' % (exc,))
    result.update(returncode=rc, elapsed_s=round(time.time() - t0, 2),
                  end=_now())
    res.write_text(json.dumps(result, indent=1))
    path.rename(DONE / path.name)
    print('[%s] DONE %s rc=%s (%.1fs)' % (_now(), jid, rc, result['elapsed_s']))


def main() -> int:
    if os.geteuid() == 0:
        print('labrunner: refusing to run as root')
        return 1
    for d in (QUEUE, DONE, OUT):
        d.mkdir(parents=True, exist_ok=True)
    if STOP.exists():
        STOP.unlink()
    (BASE / 'HEARTBEAT').write_text(_now())
    print('PRIMA labrunner on %s — watching %s  (Ctrl-C to stop)'
          % (os.uname().nodename, QUEUE))
    try:
        while not STOP.exists():
            (BASE / 'HEARTBEAT').write_text(_now())
            jobs = sorted(QUEUE.glob('*.json'))
            for j in jobs:
                if STOP.exists():
                    break
                run_job(j)
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        pass
    print('labrunner stopped')
    return 0


if __name__ == '__main__':
    sys.exit(main())
