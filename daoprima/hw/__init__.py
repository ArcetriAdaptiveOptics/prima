"""Hardware backends for DaoPrima (DAO / daoHw-shaped).

BMC Multi-DM is driven like daoEkarus ``daodmAlpaoCtrl`` / daoHw meadowlark:
a small process opens the vendor device and applies shapes from a command SHM.
"""
from daoprima.hw.bmc_dm import BmcMultiDm, open_bmc_dm, probe_bmc_usb

__all__ = ['BmcMultiDm', 'open_bmc_dm', 'probe_bmc_usb']
