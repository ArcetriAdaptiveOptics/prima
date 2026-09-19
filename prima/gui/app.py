"""Entry point: prima-gui"""
import argparse
import os
import sys


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(description='Prima Drop 1 main GUI')
    parser.add_argument(
        '--screenshot', metavar='PATH',
        help='Render once offscreen and save a PNG, then exit')
    parser.add_argument(
        '--screenshot-sync', metavar='PATH',
        help='Run beat sweep then save PNG and exit')
    parser.add_argument(
        '--platform', default=None,
        help='Qt platform plugin (default: env or xcb; use offscreen for CI)')
    args, qt_args = parser.parse_known_args(argv)

    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot or args.screenshot_sync:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    # QApplication wants sys.argv-like list starting with program name
    from prima.gui.main_window import build_app
    app, win = build_app(['prima-gui'] + qt_args, demo=True)

    if args.screenshot or args.screenshot_sync:
        app.processEvents()
        if args.screenshot_sync:
            # mismatch then sweep for a more informative plot
            win._lock_exp.setChecked(False)
            win._exp_spin.setValue(40.0)
            win._freq_spin.setValue(20.0)
            win._on_exposure_changed()
            win._run_sync_sweep()
            app.processEvents()
            path = args.screenshot_sync
        else:
            path = args.screenshot
        # let a few frames render
        for _ in range(5):
            win._on_tick()
            app.processEvents()
        pix = win.grab()
        ok = pix.save(path)
        print('screenshot_saved=%s path=%s size=%sx%s' % (
            ok, path, pix.width(), pix.height()))
        return 0 if ok else 1

    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
