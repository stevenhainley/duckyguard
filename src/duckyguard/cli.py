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
    li = sub.add_parser("incidents", help="list saved incidents")
    li.add_argument("--json", action="store_true", help="one JSON object per line, for scripts")
    ex = sub.add_parser("export", help="export one incident as Markdown or OCSF JSON")
    ex.add_argument("incident_id")
    ex.add_argument("--format", choices=["md", "ocsf"], default="md")
    sub.add_parser("bench", help="run the simulation harness")
    sub.add_parser("selftest", help="headless software self-test (no permissions needed)")
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
            if args.json:
                v = inc.get("verdict") or {}
                print(json.dumps({"id": inc["id"], "started_at": inc.get("started_at"), "summary": inc.get("summary", ""),
                                  "rule": str((v.get("features") or {}).get("rule") or ""), "kind": v.get("kind", ""),
                                  "keys_reached_app": inc.get("keys_before_block", 0), "keys_dropped": inc.get("blocked_count", 0),
                                  "keyboard": (inc.get("keyboard") or {}).get("product", ""), "simulated": bool(inc.get("simulated"))}))
            else:
                print(f"{inc['id']}  {inc.get('summary', '')}")
        return 0

    if args.cmd == "export":
        from .incidents import export_incident, export_incident_ocsf
        from .store import Store
        s = Store()
        inc = s.get_incident(args.incident_id)
        if not inc:
            print("no such incident", file=sys.stderr)
            return 1
        print((export_incident_ocsf if args.format == "ocsf" else export_incident)(inc, s.exports_dir, __version__))
        return 0

    if args.cmd == "selftest":
        from .selftest import run
        return run()

    if args.cmd == "bench":
        import runpy
        import os
        runpy.run_path(os.path.join(os.path.dirname(__file__), "..", "..", "bench", "simulate.py"), run_name="__main__")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
