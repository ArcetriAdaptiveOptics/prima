
"""Thin shims so ported Prisma modules use plico utilities."""
from plico.utils.logger import Logger
from plico.utils.snapshotable import Snapshotable
from plico.utils.decorator import (
    returns, returnsNone, returnsForExample, override,
    logEnterAndExit, logTime, cacheResult, suppressException,
)

def logFailureAndRaise(f):
    return f

def logFailureAndContinue(f):
    return f
