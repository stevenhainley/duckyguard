"""
DuckyGuard command line.

    duckyguard app                 menu bar app (default)
    duckyguard start               protection in the foreground, text output
    duckyguard status              permissions, keyboards, trusted devices
    duckyguard devices [...]       list keyboards + fingerprints, export/import trust policy
    duckyguard audit [...]         inspect or verify the SHA-256 hash-chained audit.jsonl log
    duckyguard lockdown [on|off]   check or toggle external-keyboard lockdown mode
    duckyguard simulate [...]      type a harmless payload at machine speed
    duckyguard incidents           list saved incidents
    duckyguard export <id>         write a Markdown or OCSF report for one incident
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
    dev = sub.add_parser("devices", help="list keyboards with SHA-256 fingerprints or manage trusted devices")
    dev.add_argument("--json", action="store_true", help="print JSON inventory and trusted devices")
    dev.add_argument("--export", dest="export_path", metavar="PATH", help="export trusted devices to a JSON file")
    dev.add_argument("--import", dest="import_path", metavar="PATH", help="import trusted devices from a JSON file")
    dev.add_argument("--replace", action="store_true", help="with --import: replace existing trust list instead of merging")
    dev.add_argument("--trust", metavar="KEY", help="trust a keyboard by its device key")
    dev.add_argument("--untrust", metavar="KEY", help="remove a keyboard from the trust list")
    aud = sub.add_parser("audit", help="inspect or verify the tamper-evident audit.jsonl log")
    aud.add_argument("--json", action="store_true", help="print one JSON audit record per line")
    aud.add_argument("--limit", type=int, default=50, help="number of recent entries to print (0 for all)")
    aud.add_argument("--verify", action="store_true", help="verify SHA-256 hash chain across audit.jsonl")
    ld = sub.add_parser("lockdown", help="inspect or toggle Lockdown mode for external keyboards")
    ld.add_argument("state", nargs="?", choices=["on", "off", "status"], default="status")
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
            "lockdown_mode": bool(s.get("lockdown_mode", False)),
            "audit": s.verify_audit(),
            "keyboards": [k.as_dict() for k in enumerate_keyboards()],
            "trusted": s.trusted_devices(),
            "settings": s.settings(),
            "data_dir": s.root,
        }, indent=2))
        return 0

    if args.cmd == "devices":
        from .devices import enumerate_keyboards, identity_flags
        from .store import Store
        s = Store()
        if args.export_path:
            payload = s.export_trusted_devices(args.export_path)
            print(json.dumps({"exported": len(payload["devices"]), "path": args.export_path}))
            return 0
        if args.import_path:
            try:
                count = s.import_trusted_devices(args.import_path, merge=not args.replace)
            except (OSError, ValueError) as e:
                print(f"could not import trusted devices: {e}", file=sys.stderr)
                return 1
            print(json.dumps({"imported": count, "merge": not args.replace}))
            return 0
        present = enumerate_keyboards()
        if args.trust:
            matched = next((k for k in present if k.key == args.trust), None)
            s.trust_device(args.trust, matched.as_dict() if matched else {"key": args.trust, "product": args.trust})
            s.append_audit("device_trusted_cli", {"key": args.trust})
            print(f"trusted {args.trust}")
            return 0
        if args.untrust:
            s.untrust_device(args.untrust)
            s.append_audit("device_untrusted_cli", {"key": args.untrust})
            print(f"untrusted {args.untrust}")
            return 0
        trusted = s.trusted_devices()
        rows = []
        for k in present:
            d = k.as_dict()
            d["trusted"] = k.built_in or s.is_trusted(k.key)
            d["flags"] = identity_flags(k, present, trusted)
            rows.append(d)
        if args.json:
            print(json.dumps({"connected": rows, "trusted": trusted}, indent=2))
        else:
            for d in rows:
                tag = "built-in" if d["built_in"] else ("trusted" if d["trusted"] else "untrusted")
                flags = f"  flags={','.join(d['flags'])}" if d["flags"] else ""
                note = f"  [{d['vendor_note']}]" if d.get("vendor_note") else ""
                print(f"{d['vendor_hex']}:{d['product_hex']}  {d['transport']:<9}  {tag:<9}  pin={d['fingerprint_short']}  {d['product']}{note}{flags}")
        return 0

    if args.cmd == "audit":
        from .store import Store
        s = Store()
        if args.verify:
            res = s.verify_audit()
            print(json.dumps(res, indent=2))
            return 0 if res["ok"] else 1
        for rec in s.read_audit(limit=args.limit):
            if args.json:
                print(json.dumps(rec, sort_keys=True))
            else:
                det = " ".join(f"{k}={v}" for k, v in (rec.get("details") or {}).items() if v not in ("", None, [], {}))
                print(f"#{rec.get('seq', 0):04d}  {rec.get('iso', '')}  {rec.get('event', ''):<24}  {det}".rstrip())
        return 0

    if args.cmd == "lockdown":
        from .store import Store
        s = Store()
        if args.state in ("on", "off"):
            on = args.state == "on"
            s.set("lockdown_mode", on)
            s.append_audit("lockdown_changed", {"enabled": on, "source": "cli"})
        print(json.dumps({"lockdown_mode": bool(s.get("lockdown_mode", False))}))
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
