"""READ-ONLY dump of the E-518 state (no set commands)."""
import time
from prima.hardware.gcs_tcp import GcsTcp

g = GcsTcp('192.168.30.190', 50000)
g.connect()
print('IDN', g.idn())
for q in ['SAI?', 'ONL?', 'SVO?', 'SVA?', 'MOV?', 'POS?', 'VOL?', 'TMN?', 'TMX?', 'NLM?', 'PLM?',
          'VMI?', 'VMA?', 'WGO?', 'WSL?', 'WTR?', 'OVF?', 'ERR?']:
    r = g.query(q, wait_s=0.6).strip().replace('\n', ' | ')
    print('%-5s %s' % (q, r))
vols = []
for i in range(20):
    vols.append(g.query('VOL?', wait_s=0.3).strip().replace('\n', ' '))
    time.sleep(0.013)
print('VOL samples:'); print('\n'.join(vols))
pos = []
for i in range(20):
    pos.append(g.query('POS?', wait_s=0.3).strip().replace('\n', ' '))
    time.sleep(0.013)
print('POS samples:'); print('\n'.join(pos))
g.close()
