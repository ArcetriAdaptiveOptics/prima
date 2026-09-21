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
    parser.add_argument(
        '--live-aravis', action='store_true',
        help='Connect Aravis GigE camera (Manta) before screenshot / run')
    parser.add_argument(
        '--aravis-ip', default='192.168.30.189',
        help='GigE camera IP for --live-aravis / Connect live fallback')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)

    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot or args.screenshot_sync or args.screenshot_measure:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    from prima.gui.main_window import build_app
    from prima.gui.sync_dialog import SyncDialog
    app, win = build_app(['prima-gui'] + qt_args, demo=True)

    if args.live_aravis:
        # Camera via Aravis (Vimba/pysilico often unavailable). Still try
        # ModulatorClient on :7030 so E-518 can be live if server is up.
        from prima.gui.aravis_camera import connect_aravis
        from prima.gui.live_clients import connect_modulator
        try:
            cam = connect_aravis(args.aravis_ip)
        except Exception as e:
            print('live_aravis_failed: %s' % e)
            return 2
        win._camera = cam
        live_mod = None
        mod_err = None
        try:
            m = connect_modulator()
            _ = m.getStatus()
            live_mod = m
        except Exception as e:
            mod_err = e
        if live_mod is not None:
            win._modulator = live_mod
            win._engine.rebind(camera=cam, modulator=live_mod)
            try:
                mod_name = live_mod.name()
            except Exception:
                mod_name = 'live@7030'
            win._server_status.setText(
                'LIVE  cam=%s  mod=%s' % (cam.name(), mod_name))
            print('live_aravis_ok cam=%s mod=live' % cam.name(), flush=True)
            win._pull_mod_to_spins()
            win._apply_modulator()
        else:
            win._engine.rebind(camera=cam, modulator=None)
            win._server_status.setText(
                'LIVE  cam=%s  mod=DEMO (no :7030 — Start lab + Connect live)%s'
                % (cam.name(),
                   ('\n%s' % mod_err) if mod_err else ''))
            print('live_aravis_ok cam=%s mod=demo (%s)' % (
                cam.name(), mod_err), flush=True)
        win._using_live = True
        sys.stdout.flush()
        # Raise window on the current display
        win.show()
        win.raise_()
        win.activateWindow()
        app.processEvents()

    if args.screenshot or args.screenshot_sync or args.screenshot_measure:
        app.processEvents()
        # More ticks when live so first real frames arrive
        n_ticks = 40 if args.live_aravis else 8
        for _ in range(n_ticks):
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
