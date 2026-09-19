"""Entry point: prima-gui"""
import argparse
import os
import sys


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description='Prima Drop 1 main GUI')
    parser.add_argument('--screenshot', metavar='PATH')
    parser.add_argument(
        '--screenshot-sync', metavar='PATH',
        help='Open sync popup, run sweep, grab popup')
    parser.add_argument(
        '--screenshot-measure', metavar='PATH',
        help='Run one Take Measure then screenshot main window')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)

    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot or args.screenshot_sync or args.screenshot_measure:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    from prima.gui.main_window import build_app
    from prima.gui.sync_dialog import SyncDialog
    app, win = build_app(['prima-gui'] + qt_args, demo=True)

    if args.screenshot or args.screenshot_sync or args.screenshot_measure:
        app.processEvents()
        for _ in range(8):
            win._on_tick()
            app.processEvents()

        if args.screenshot_measure:
            win._on_find_pupils()
            app.processEvents()
            win._on_take_once()
            app.processEvents()
            for _ in range(4):
                win._on_tick()
                app.processEvents()
            path = args.screenshot_measure
            pix = win.grab()
        elif args.screenshot_sync:
            dlg = SyncDialog(
                win, win._camera,
                get_exposure_ms=lambda: win._exp_spin.value(),
                apply_match_cb=win._apply_sync_match)
            dlg.setStyleSheet(win.styleSheet())
            dlg.show()
            app.processEvents()
            win._lock_exp.setChecked(False)
            win._exp_spin.setValue(40.0)
            win._on_exposure_changed()
            dlg._run_sweep()
            app.processEvents()
            path = args.screenshot_sync
            pix = dlg.grab()
            dlg.close()
        else:
            path = args.screenshot
            pix = win.grab()

        ok = pix.save(path)
        print('screenshot_saved=%s path=%s size=%sx%s' % (
            ok, path, pix.width(), pix.height()))
        return 0 if ok else 1

    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
