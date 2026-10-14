"""Find the control sequence that makes the Multi driver CONSUME frames.
Only the factory flat is ever sent.  Each variant starts from a USB reset."""
import time
import numpy as np
import usb.core, usb.util
from daoprima.hw import bmc_constants as C
from daoprima.hw.bmc_usb import load_map, pack_frame
from prima.aolab.devices.hw import load_flat, FACTORY_FLAT

flat = load_flat(FACTORY_FLAT)
frame = pack_frame(flat, load_map('MULTI140.map'))
CODES = dict(FS1=0, FS0=1, FRESET1=2, FRESET0=3, HV1=4, HV0=5, LVSHDN1=6, LVSHDN0=7)

def open_dev(reset=True):
    d = usb.core.find(idVendor=C.BMC_MULTI_VID, idProduct=C.BMC_MULTI_PID)
    if reset:
        d.reset(); time.sleep(1.5)
        d = usb.core.find(idVendor=C.BMC_MULTI_VID, idProduct=C.BMC_MULTI_PID)
    try:
        if d.is_kernel_driver_active(0): d.detach_kernel_driver(0)
    except Exception: pass
    d.set_configuration(); usb.util.claim_interface(d, 0)
    return d

def ctrl(d, name):
    d.ctrl_transfer(0x40, C.VR_SET_CONTROL, 0, CODES[name], None, timeout=1000)
    time.sleep(0.01)

def status(d):
    try: return bytes(d.ctrl_transfer(0xC0, C.VR_GET_STATUS, 0, 0, 2, timeout=500)).hex()
    except Exception as e: return 'err %s' % e

def nframes(d, n=12, fs=False):
    ok = 0
    for i in range(n):
        try:
            if fs: ctrl(d, 'FS1')
            d.write(0x02, frame, timeout=300)
            if fs: ctrl(d, 'FS0')
            ok += 1
        except usb.core.USBTimeoutError:
            break
        time.sleep(0.02)
    return ok

variants = {
 'cursor (reset_all, FRESET0, FRESET1, HV1)': ['RESETALL', 'FRESET0', 'FRESET1', 'HV1'],
 'FRESET pulse ending low, HV1':               ['RESETALL', 'FRESET1', 'FRESET0', 'HV1'],
 'LV_SHDN0 + FRESET pulse low + HV1':          ['RESETALL', 'LVSHDN0', 'FRESET1', 'FRESET0', 'HV1'],
 'LV_SHDN0 + cursor':                          ['RESETALL', 'LVSHDN0', 'FRESET0', 'FRESET1', 'HV1'],
 'cursor + frame sync per frame':              ['RESETALL', 'FRESET0', 'FRESET1', 'HV1', '+FS'],
 'FRESET low + frame sync per frame':          ['RESETALL', 'FRESET1', 'FRESET0', 'HV1', '+FS'],
}
for name, seq in variants.items():
    d = open_dev(reset=True)
    fs = False
    for s in seq:
        if s == 'RESETALL':
            d.ctrl_transfer(0x40, C.VR_RESET_ALL, 0, 0, None, timeout=1000); time.sleep(0.02)
        elif s == '+FS':
            fs = True
        else:
            ctrl(d, s)
    st0 = status(d)
    n = nframes(d, 12, fs)
    print('%-45s status %s -> %s  frames accepted %d/12' % (name, st0, status(d), n), flush=True)
    try: ctrl(d, 'HV0')
    except Exception: pass
    usb.util.release_interface(d, 0); usb.util.dispose_resources(d)
    if n == 12:
        print('==> WORKS:', name)
