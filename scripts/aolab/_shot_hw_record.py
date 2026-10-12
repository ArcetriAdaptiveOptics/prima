# GUI on the real bench: pupils -> ROI -> reference -> IM -> turbulence ->
# loop g=0.5 -> RECORD button (2048 frames + 20 camera frames) -> screenshots
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
    win.sp_nmodes_cal.setValue(50); win._on_calibrate()
    QtCore.QTimer.singleShot(2000, wait)
def wait():
    if e.calibrating:
        QtCore.QTimer.singleShot(500, wait); return
    win.sp_trms.setValue(180); win.sp_wind.setValue(0.5); win.chk_turb.setChecked(True)
    win.sp_gain.setValue(0.5); win.sp_leak.setValue(1.0)
    e.close_loop()
    QtCore.QTimer.singleShot(6000, s4)
def s4():
    win.sp_rec_n.setValue(2048); win.sp_rec_cam.setValue(20)
    win.ed_rec_label.setText('gui-g0.5-turb180')
    win.b_rec.click()
    QtCore.QTimer.singleShot(20000, s5)
def s5():
    win.grab().save(OUT + 'gui_hw_recording.png')
    QtCore.QTimer.singleShot(1000, s6)
def s6():
    r = e.last_recording
    if e.recording or r is None or not r.done.is_set():
        QtCore.QTimer.singleShot(1000, s6); return
    QtCore.QTimer.singleShot(1500, s7)
def s7():
    win.grab().save(OUT + 'gui_hw_recorded.png')
    r = e.last_recording
    print(json.dumps({'path': str(r.path), 'n': r.n, 'error': r.error,
                      'rate': e.loop_rate_hz(), 'roi': e.cam.get_roi()}),
          flush=True)
    win.chk_turb.setChecked(False)
    win.close()
QtCore.QTimer.singleShot(4000, s1)
