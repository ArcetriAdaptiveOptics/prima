"""BMC Multi USB diagnostics: status, firmware, repeated flat frames."""
import time, sys
import numpy as np
import usb.core, usb.util
from daoprima.hw import bmc_constants as C
from daoprima.hw.bmc_usb import MultiDmUsb
from prima.aolab.devices.hw import load_flat, FACTORY_FLAT, dm_owner_pids

print('owners', dm_owner_pids())
flat = load_flat(FACTORY_FLAT)
dev = usb.core.find(idVendor=C.BMC_MULTI_VID, idProduct=C.BMC_MULTI_PID)
print('dev', dev is not None, 'bus', dev.bus, 'addr', dev.address)
if '--reset' in sys.argv:
    print('usb reset'); dev.reset(); time.sleep(2.0)
m = MultiDmUsb()
m.open(initial=flat)
d = m._dev
for name, req, ln in (('FW', C.VR_GET_FIRMWARE_VER, 2), ('STATUS', C.VR_GET_STATUS, 2)):
    try:
        print(name, bytes(d.ctrl_transfer(0xC0, req, 0, 0, ln, timeout=1000)).hex())
    except Exception as e:
        print(name, 'ERR', e)
print('cable_ok', m.cable_ok(), 'status bits 0x%04x (bit1=HV active)' % m.status_bits(), 'hv warning', getattr(m, '_hv_warning', None))
print('ep', hex(m._ep_out.bEndpointAddress), 'maxpkt', m._ep_out.wMaxPacketSize)
ok = 0
for i in range(20):
    t = time.time()
    try:
        m.send_data(flat)
        ok += 1
        print('frame %d ok %.1f ms' % (i, 1e3 * (time.time() - t)))
    except Exception as e:
        print('frame %d ERR %s after %.0f ms' % (i, e, 1e3 * (time.time() - t)))
        try:
            print('  STATUS', bytes(d.ctrl_transfer(0xC0, C.VR_GET_STATUS, 0, 0, 2, timeout=1000)).hex())
        except Exception as e2:
            print('  status err', e2)
    time.sleep(0.05)
print('ok frames', ok, 'status 0x%04x' % m.status_bits())
m.close()
