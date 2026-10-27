"""
DuckyGuard command line.

    duckyguard app                 menu bar app (default)
    duckyguard start               protection in the foreground, text output
    duckyguard status              permissions, keyboards, trusted devices
    duckyguard simulate [...]      type a harmless payload at machine speed
    duckyguard incidents           list saved incidents
    duckyguard export <id>         write a Markdown report for one incident
    duckyguard bench               simulation harness (docs/EVALUATION.md)
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import __version__


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="duckyguard", description="DuckyGuard: keystroke-injection protection for macOS")
    ap.add_argument("--version", action="version", version=f"duckyguard {__version__}")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("app", help="menu bar app (default)")
    sub.add_parser("start", help="protection in the foreground")
    sub.add_parser("status", help="permissions and keyboards")
    sim = sub.add_parser("simulate", help="type a harmless payload at machine speed")
    sim.add_argument("--preset", choices=["harmless", "plain", "human"], default="harmless")
    sim.add_argument("--interval", type=float, default=12.0, help="ms between keys")
    sim.add_argument("--delay", type=float, default=3.0, help="seconds before typing starts")
    sub.add_parser("incidents", help="list saved incidents")
    ex = sub.add_parser("export", help="export one incident as Markdown")
    ex.add_argument("incident_id")
    sub.add_parser("bench", help="run the simulation harness")
    args = ap.parse_args(argv)

    if args.cmd in (None, "app"):
        from .app import run_app
        run_app()
        return 0

    if args.cmd == "start":
        from .engine import Engine
        eng = Engine(on_event=lambda e: print(json.dumps({k: v for k, v in e.items() if k != "incident"})))
        st = eng.start()
        print(f"DuckyGuard {__version__}: {st}")
        if st in ("no_permission", "error"):
            print("Grant Input Monitoring and Accessibility to this terminal in System Settings > Privacy & Security.")
            return 2
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            eng.stop(persist=False)
        return 0

    if args.cmd == "status":
        from . import permissions
        from .devices import enumerate_keyboards
        from .store import Store
        s = Store()
        print(json.dumps({
            "version": __version__,
            "permissions": permissions.status(),
            "keyboards": [k.as_dict() for k in enumerate_keyboards()],
            "trusted": s.trusted_devices(),
            "settings": s.settings(),
            "data_dir": s.root,
        }, indent=2))
        return 0

    if args.cmd == "simulate":
        from .simulator import BadUSBSimulator
        print(f"typing '{args.preset}' preset in {args.delay:.0f}s at {args.interval:.0f} ms/key; "
              "focus a harmless text field")
        BadUSBSimulator().run(preset=args.preset, interval_ms=args.interval, human=(args.preset == "human"),
                              countdown=args.delay)
        return 0

    if args.cmd == "incidents":
        from .store import Store
        for inc in Store().list_incidents():
            print(f"{inc['id']}  {inc.get('summary', '')}")
        return 0

    if args.cmd == "export":
        from .incidents import export_incident
        from .store import Store
        s = Store()
        inc = s.get_incident(args.incident_id)
        if not inc:
            print("no such incident", file=sys.stderr)
            return 1
        print(export_incident(inc, s.exports_dir, __version__))
        return 0

    if args.cmd == "bench":
        import runpy
        import os
        runpy.run_path(os.path.join(os.path.dirname(__file__), "..", "..", "bench", "simulate.py"), run_name="__main__")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
