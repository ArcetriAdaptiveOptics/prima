"""Shared CLI helpers for flattening visibility scripts."""
from __future__ import annotations

import argparse
from pathlib import Path

STORE_MEDIA = Path(
    '/home/labot/.local/state/cursor/agent-stores/'
    'cursor_agent_stores/bc-ecf861ba-b2d0-4997-844e-b6d177afd5c9/files/media')
STORE_INTERNAL = Path(
    '/home/labot/.local/state/cursor/agent-stores/'
    'cursor_agent_stores/bc-ecf861ba-b2d0-4997-844e-b6d177afd5c9/files/internal')


def add_apply_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        '--dry-run', action='store_true', default=True,
        help='No real DM moves (default)')
    p.add_argument(
        '--apply', action='store_true',
        help='Enable real DM / HW moves (overrides --dry-run)')


def is_dry_run(args) -> bool:
    return not bool(getattr(args, 'apply', False))


def media_path(name: str) -> Path:
    STORE_MEDIA.mkdir(parents=True, exist_ok=True)
    return STORE_MEDIA / name


def internal_path(name: str) -> Path:
    STORE_INTERNAL.mkdir(parents=True, exist_ok=True)
    return STORE_INTERNAL / name
