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
        help='Connect live Aravis Manta + direct PI E-518 GCS')
    parser.add_argument(
        '--live', action='store_true',
        help='Same as --live-aravis (Drop 1 live stack)')
    parser.add_argument(
        '--aravis-ip', default=os.environ.get('PRIMA_ARAVIS_IP', '192.168.30.189'),
        help='GigE camera IP for Aravis')
    parser.add_argument(
        '--e518-host', default=os.environ.get('PRIMA_E518_HOST', '192.168.30.190'),
        help='PI E-518 host for direct GCS modulator')
    parser.add_argument(
        '--e518-port', type=int,
        default=int(os.environ.get('PRIMA_E518_PORT', '50000')),
        help='PI E-518 GCS TCP port')
    parser.add_argument('--platform', default=None)
    args, qt_args = parser.parse_known_args(argv)

    if args.platform:
        os.environ['QT_QPA_PLATFORM'] = args.platform
    elif args.screenshot or args.screenshot_sync or args.screenshot_measure:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    from prima.gui.main_window import build_app
    from prima.gui.sync_dialog import SyncDialog
    app, win = build_app(['prima-gui'] + qt_args, demo=True)

    want_live = bool(args.live_aravis or args.live)
    if want_live:
        from prima.gui.live_clients import try_connect_live
        cam, mod, errors = try_connect_live(
            aravis_ip=args.aravis_ip,
            e518_host=args.e518_host,
            e518_port=args.e518_port,
        )
        if cam is None:
            print('live_camera_failed: %s' % ('; '.join(errors) or 'unknown'))
            return 2
        live_mod = None
        if mod is not None:
            try:
                _ = mod.getStatus()
                live_mod = mod
            except Exception as e:
                errors.append('modulator(probe): %s' % e)
                live_mod = None
        win._camera = cam
        if live_mod is not None:
            win._modulator = live_mod
            win._engine.rebind(camera=cam, modulator=live_mod)
            try:
                mod_name = live_mod.name()
            except Exception:
                mod_name = type(live_mod).__name__
            win._server_status.setText(
                'LIVE  cam=%s  mod=%s' % (cam.name(), mod_name))
            print('live_ok cam=%s mod=%s' % (cam.name(), mod_name), flush=True)
            win._pull_mod_to_spins()
            win._apply_modulator()
        else:
            win._engine.rebind(camera=cam, modulator=None)
            win._server_status.setText(
                'LIVE  cam=%s  mod=DEMO%s'
                % (cam.name(),
                   ('\n' + '; '.join(errors)) if errors else ''))
            print('live_ok cam=%s mod=demo (%s)' % (
                cam.name(), '; '.join(errors)), flush=True)
        win._using_live = True
        win._sync_exposure_spin_enabled()
        if win._lock_exp.isChecked():
            win._apply_exp_from_freq()
        sys.stdout.flush()
        win.show()
        win.raise_()
        win.activateWindow()
        app.processEvents()

    if args.screenshot or args.screenshot_sync or args.screenshot_measure:
        app.processEvents()
        # More ticks when live so first real frames arrive
        n_ticks = 40 if want_live else 8
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
            win._sync_exposure_spin_enabled()
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
