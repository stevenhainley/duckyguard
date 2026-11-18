"""
Build DuckyGuard.app with py2app (unsigned, reproducible from this repo).

    .venv/bin/python packaging/setup_py2app.py py2app --dist-dir dist --bdist-base build/py2app

See packaging/build.sh for the full build + DMG script and docs/INSTALL.md
for the Gatekeeper steps an unsigned app needs.
"""
import os
import sys

from setuptools import setup

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from duckyguard import __version__  # noqa: E402

PLIST = {
    "CFBundleName": "DuckyGuard",
    "CFBundleDisplayName": "DuckyGuard",
    "CFBundleIdentifier": "co.shindustries.duckyguard",
    "CFBundleShortVersionString": __version__,
    "CFBundleVersion": __version__,
    "LSMinimumSystemVersion": "26.0",   # bundled Homebrew Python 3.14 has minos 26.0 (checked with vtool)
    "LSUIElement": True,                       # menu bar app: no Dock icon
    "NSHumanReadableCopyright": "MIT License. Steven Hainley, sh. industries.",
    "NSHighResolutionCapable": True,
    "NSSupportsAutomaticGraphicsSwitching": True,
    # Shown by macOS next to the permission prompts.
    "NSInputMonitoringUsageDescription": "DuckyGuard times keystrokes to tell a hand from a scripted keyboard. It keeps the text only of bursts it blocks.",
    "NSAccessibilityUsageDescription": "DuckyGuard needs Accessibility to block keystrokes from a device that types like a machine.",
}

setup(
    name="DuckyGuard",
    app=[os.path.join(HERE, "duckyguard_app.py")],
    options={
        "py2app": {
            "iconfile": os.path.join(ROOT, "assets", "AppIcon.icns"),
            "plist": PLIST,
            "packages": ["duckyguard", "rumps", "pynput"],
            "includes": ["objc", "AppKit", "Foundation", "WebKit", "Quartz", "ApplicationServices", "ctypes", "plistlib"],
            "excludes": ["PIL", "pytest", "hypothesis", "tkinter", "setuptools", "pip"],
            "argv_emulation": False,
            "strip": True,
            "optimize": 1,
        }
    },
    setup_requires=["py2app"],
)
