"""Read-only probe of the Manta: features, timing, one frame saved to work/data."""
import sys, time, json
from pathlib import Path
import numpy as np
import gi
gi.require_version('Aravis', '0.8')
from gi.repository import Aravis

ip = sys.argv[1] if len(sys.argv) > 1 else '192.168.30.189'
out = Path.home() / 'git/prima/work/data'; out.mkdir(parents=True, exist_ok=True)
cam = Aravis.Camera.new(ip)
dev = cam.get_device()
info = {}
for f in ['DeviceModelName', 'DeviceFirmwareVersion', 'PixelFormat', 'Width', 'Height', 'OffsetX', 'OffsetY',
          'BinningHorizontal', 'BinningVertical', 'ExposureTimeAbs', 'Gain', 'GainRaw', 'AcquisitionFrameRateAbs',
          'AcquisitionFrameRateLimit', 'StreamBytesPerSecond', 'GevSCPSPacketSize', 'TriggerSource',
          'TriggerMode', 'ExposureAuto', 'GainAuto', 'SensorWidth', 'SensorHeight', 'WidthMax', 'HeightMax']:
    v = None
    for getter in (dev.get_integer_feature_value, dev.get_float_feature_value, dev.get_string_feature_value):
        try:
            v = getter(f); break
        except Exception:
            pass
    info[f] = v
try:
    info['binning_bounds'] = list(cam.get_binning_bounds() if hasattr(cam,'get_binning_bounds') else [])
except Exception as e:
    info['binning_bounds'] = str(e)
try:
    info['fps_bounds'] = list(cam.get_frame_rate_bounds())
except Exception as e:
    info['fps_bounds'] = str(e)
print(json.dumps(info, indent=1, default=str))
# grab a few frames with current settings, measure rate
PKT = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
cam.gv_set_packet_size(PKT)
PF = sys.argv[3] if len(sys.argv) > 3 else 'Mono12'
cam.set_string('PixelFormat', PF)
cam.set_string('ExposureAuto', 'Off')
cam.set_string('GainAuto', 'Off')
EXP = float(sys.argv[4]) if len(sys.argv) > 4 else 15000.0
cam.set_float('ExposureTimeAbs', EXP)
try:
    stream_opts = None
except Exception:
    pass
print('packet size now', cam.gv_get_packet_size())
cam.set_acquisition_mode(Aravis.AcquisitionMode.CONTINUOUS)
stream = cam.create_stream(None, None)
try:
    stream.set_property('packet-resend', 0)
except Exception as e:
    print('resend prop', e)
payload = cam.get_payload()
for _ in range(6):
    stream.push_buffer(Aravis.Buffer.new_allocate(payload))
cam.start_acquisition()
t0 = time.time(); frames = []; n_err = 0
while time.time() - t0 < 6 and len(frames) < 20:
    b = stream.timeout_pop_buffer(2000000)
    if b is None:
        continue
    if b.get_status() == Aravis.BufferStatus.SUCCESS:
        x, y, w, h = cam.get_region()
        d = np.frombuffer(b.get_data(), dtype=np.uint8 if b.get_image_pixel_format() == 0x01080001 else '<u2')
        frames.append((time.time(), d[: w * h].reshape(h, w).copy()))
    else:
        n_err += 1
    stream.push_buffer(b)
cam.stop_acquisition()
ts = [f[0] for f in frames]
print('frames', len(frames), 'errors', n_err, 'fps %.2f' % ((len(ts) - 1) / (ts[-1] - ts[0]) if len(ts) > 1 else 0))
img = np.mean([f[1] for f in frames[-5:]], axis=0)
np.save(out / 'probe_frame.npy', img.astype(np.float32))
print('frame', img.shape, 'min %.0f max %.0f mean %.1f p99 %.0f' % (img.min(), img.max(), img.mean(), np.percentile(img, 99)))
try:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    plt.figure(figsize=(7, 7)); plt.imshow(img, origin='lower', cmap='inferno'); plt.colorbar()
    plt.title('Manta probe %s' % time.strftime('%Y-%m-%d %H:%M')); plt.savefig(out / 'probe_frame.png', dpi=80)
except Exception as e:
    print('png failed', e)
