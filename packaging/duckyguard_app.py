"""py2app entry point for the DuckyGuard menu bar app."""
import sys

if "--self-test" in sys.argv:
    from duckyguard.selftest import run
    sys.exit(run())

from duckyguard.app import run_app

run_app()
