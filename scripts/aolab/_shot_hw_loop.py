# GUI demo on the real bench: pupils -> ROI -> reference -> IM -> loop -> turbulence
import json
OUT = '/home/labot/git/prima/work/figs/'
def s1():
    win._on_find_pupils()
    QtCore.QTimer.singleShot(1500, s2)
def s2():
    e.roi_to_pupils(5); win._draw_pupils()
    QtCore.QTimer.singleShot(2000, s3)
def s3():
    e.set_reference(20)
    win.sp_nmodes_cal.setValue(60); win.sp_amp.setValue(108); win._on_calibrate()
    QtCore.QTimer.singleShot(2000, wait)
def wait():
    if e.calibrating:
        QtCore.QTimer.singleShot(500, wait); return
    win.grab().save(OUT + 'gui_hw_calibrated.png')
    win.sp_trms.setValue(150); win.sp_wind.setValue(0.3); win.chk_turb.setChecked(True)
    QtCore.QTimer.singleShot(8000, s4)
def s4():
    win.grab().save(OUT + 'gui_hw_turb_open.png')
    e.close_loop()
    QtCore.QTimer.singleShot(10000, s5)
def s5():
    win.grab().save(OUT + 'gui_hw_turb_closed.png')
    print(json.dumps({'rate': e.loop_rate_hz(), 'cam_fps': e.cam.get_fps(), 'compute_ms': e.compute_time_ms(), 'roi': e.cam.get_roi()}))
    win.close()
QtCore.QTimer.singleShot(4000, s1)
