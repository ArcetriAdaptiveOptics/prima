"""Set up E-518 like pi_gcs.TipTilt2Axis (pivot 100 V) and verify centring.
Ends at R = 0 (DC, mid travel) unless an argument R is given."""
import sys, json, time
from prima.aolab.devices.pi_modulator import PiTipTiltModulator
end_r = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
m = PiTipTiltModulator()
print('IDN', m.idn, 'servo dt', m.servo_dt, 'wtr', m.wtr)
time.sleep(0.5)
print('R=0  ', json.dumps(m.readback(20)))
for r in (5.0, 10.0, 20.0):
    m.set_modulation(r, 20.0)
    time.sleep(0.6)
    print('R=%-3g' % r, json.dumps(m.readback(60)))
m.set_modulation(end_r, 20.0)
time.sleep(0.5)
print('final R=%g' % end_r, json.dumps(m.readback(30)))
print(m.g.query('SVA?', 0.4).replace('\n', ' '), m.g.query('ERR?', 0.4))
m.close()
