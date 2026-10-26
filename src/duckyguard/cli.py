"""
DuckyGuard - Command Line Interface
Unified CLI for operating DuckyGuard daemon, running synthetic attack simulations,
and viewing automated incident response reports.
"""

import argparse
import glob
import os
import sys

from .engine import DuckyGuardEngine
from .simulator import BadUSBSimulator


def main():
    parser = argparse.ArgumentParser(
        prog="duckyguard",
        description="🛡 DuckyGuard — Autonomous Endpoint Defense Against HID Injection & BadUSB Attacks",
    )
    subparsers = parser.add_subparsers(dest="command", help="Operational mode")

    # Start command
    subparsers.add_parser("start", help="Start real-time monitoring engine in foreground")

    # GUI Desktop App command
    subparsers.add_parser("gui", help="Launch standalone DuckyGuard Desktop Application")

    # Tray command
    subparsers.add_parser("tray", help="Launch native macOS Menu Bar application")

    # Simulate command
    sim_parser = subparsers.add_parser("simulate", help="Run synthetic BadUSB attack simulation")
    sim_parser.add_argument(
        "--preset",
        choices=["resume_dropper", "reverse_shell", "powershell_enc", "benign_human"],
        default="resume_dropper",
        help="Attack scenario preset to inject",
    )
    sim_parser.add_argument(
        "--human",
        action="store_true",
        help="Simulate natural human typing velocity instead of BadUSB",
    )
    sim_parser.add_argument(
        "--delay",
        type=int,
        default=3,
        help="Countdown delay before firing keystrokes",
    )

    # Reports command
    subparsers.add_parser("reports", help="List all generated incident reports")

    args = parser.parse_args()

    if args.command == "start":
        engine = DuckyGuardEngine()
        engine.start(blocking=True)

    elif args.command == "gui" or args.command is None:
        from .desktop_app import launch_desktop
        launch_desktop()

    elif args.command == "tray":
        from .tray_app import launch_tray
        launch_tray()

    elif args.command == "simulate":
        sim = BadUSBSimulator()
        sim.run_simulation(
            preset_name=args.preset,
            is_badusb=not args.human,
            initial_countdown_sec=args.delay,
        )

    elif args.command == "reports":
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        reports_dir = os.path.join(base_dir, "reports")
        reports = sorted(glob.glob(os.path.join(reports_dir, "*.md")), reverse=True)
        if not reports:
            print("No incident reports recorded yet. Endpoint is clean.")
            return

        print(f"\n[*] Incident Reports on Record ({len(reports)}):\n")
        for r in reports:
            fname = os.path.basename(r)
            size = os.path.getsize(r)
            print(f"  📄 {fname}  ({size:,} bytes)")
        print(f"\nView details with: cat \"{reports_dir}/<filename>\"\n")


if __name__ == "__main__":
    main()
