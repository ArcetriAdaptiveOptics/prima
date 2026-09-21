"""Minimal Physikalische Instrumente GCS ASCII client over TCP.

The PI E-518 answers GCS on port 50000 without needing ``libpi_pi_gcs2.so``.
This is enough for Drop 1 tip/tilt wavegen (ONL/SVO/WAV/WSL/WGO).
"""
from __future__ import annotations

import socket
import time


class GcsTcpError(RuntimeError):
    """GCS command or connection failure."""


class GcsTcp:
    """Single persistent TCP session to a PI GCS controller.

    Reconnects automatically on connection reset / broken pipe so Drop1
    survives a prior half-open session or exclusive-control glitch.
    """

    def __init__(self, host: str, port: int = 50000, timeout_s: float = 3.0):
        self.host = str(host)
        self.port = int(port)
        self.timeout_s = float(timeout_s)
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        self.close()
        last = None
        for attempt in range(4):
            try:
                sock = socket.create_connection(
                    (self.host, self.port), timeout=self.timeout_s)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                sock.settimeout(self.timeout_s)
                self._sock = sock
                return
            except OSError as exc:
                last = exc
                time.sleep(0.3 * (attempt + 1))
        raise GcsTcpError(
            'Cannot open E-518 GCS at %s:%s: %s'
            % (self.host, self.port, last))

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def _ensure(self) -> socket.socket:
        if self._sock is None:
            self.connect()
        return self._sock

    def _reconnect(self) -> socket.socket:
        self.close()
        time.sleep(0.2)
        self.connect()
        return self._sock

    def _recv_until_idle(self, idle_s: float = 0.12, max_s: float | None = None) -> str:
        sock = self._ensure()
        max_s = self.timeout_s if max_s is None else float(max_s)
        buf = b''
        t0 = time.time()
        sock.settimeout(idle_s)
        try:
            while time.time() - t0 < max_s:
                try:
                    chunk = sock.recv(16384)
                    if not chunk:
                        break
                    buf += chunk
                except socket.timeout:
                    if buf:
                        break
                    if time.time() - t0 >= max_s:
                        break
                except (ConnectionResetError, BrokenPipeError, OSError):
                    sock = self._reconnect()
                    sock.settimeout(idle_s)
                    break
        finally:
            try:
                sock.settimeout(self.timeout_s)
            except OSError:
                pass
        return buf.decode(errors='replace')

    def query(self, command: str, wait_s: float = 0.35) -> str:
        for attempt in range(3):
            try:
                sock = self._ensure()
                sock.sendall(
                    (command.rstrip() + '\n').encode('ascii', errors='ignore'))
                return self._recv_until_idle(
                    idle_s=min(0.15, wait_s), max_s=wait_s)
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                if attempt >= 2:
                    raise GcsTcpError(
                        'GCS query failed after reconnects (%r): %s'
                        % (command, exc)) from exc
                self._reconnect()
        return ''

    def set(self, command: str, check_err: bool = True) -> int:
        """Send a set-command; optionally query ``ERR?`` (0 = OK)."""
        for attempt in range(3):
            try:
                sock = self._ensure()
                sock.sendall(
                    (command.rstrip() + '\n').encode('ascii', errors='ignore'))
                time.sleep(0.02)
                if not check_err:
                    return 0
                raw = self.query('ERR?', wait_s=0.4).strip()
                token = raw.splitlines()[0].strip() if raw else ''
                try:
                    code = int(token.split()[0])
                except (ValueError, IndexError) as exc:
                    raise GcsTcpError(
                        'Bad ERR? reply after %r: %r' % (command, raw)
                    ) from exc
                if code != 0:
                    raise GcsTcpError(
                        'GCS error %d after %r' % (code, command))
                return code
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                if attempt >= 2:
                    raise GcsTcpError(
                        'GCS set failed after reconnects (%r): %s'
                        % (command, exc)) from exc
                self._reconnect()
        return 0

    def idn(self) -> str:
        return self.query('*IDN?', wait_s=1.0).strip()
