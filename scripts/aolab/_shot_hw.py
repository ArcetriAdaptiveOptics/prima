def s1():
    win._on_find_pupils()
    QtCore.QTimer.singleShot(4000, s2)
def s2():
    p='/home/labot/git/prima/work/figs/gui_hw_nodm.png'; win.grab().save(p); print('saved', p, e.loop_rate_hz(), e.compute_time_ms()); win.close()
QtCore.QTimer.singleShot(4000, s1)
