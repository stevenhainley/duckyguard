"""
DuckyGuard - menu bar app.

A rumps status item (pixel duck, three states) plus one native window that
hosts the dashboard (local HTML in a WKWebView, no web server, no open port).
The page talks to Python through a WKScriptMessageHandler and Python pushes
JSON back with evaluateJavaScript. Everything stays inside this process.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Optional

import objc
import rumps
from AppKit import (NSApp, NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered, NSColor,
                    NSMakeRect, NSScreen, NSSound, NSWindow, NSWindowStyleMaskClosable,
                    NSWindowStyleMaskFullSizeContentView, NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
                    NSWindowStyleMaskTitled, NSWorkspace)
from Foundation import NSObject, NSURL
from WebKit import WKUserContentController, WKWebView, WKWebViewConfiguration

from . import __version__, launch_agent, permissions, updates
from .engine import Engine, STATUS_ALERT, STATUS_PAUSED, STATUS_PROTECTED, STATUS_OBSERVING
from .incidents import export_incident
from .simulator import BadUSBSimulator
from .store import Store

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
ICON_DIR = os.path.join(UI_DIR, "icons")
SUPPORT_URL: Optional[str] = None   # pay-what-you-want link; hidden in the UI until set
PROJECT_URL = "https://github.com/stevenhainley/DuckyGuard"

WINDOW_W, WINDOW_H = 820, 560


def _icon(state: str) -> str:
    name = {STATUS_PROTECTED: "protected", STATUS_OBSERVING: "protected", STATUS_ALERT: "alert"}.get(state, "paused")
    return os.path.join(ICON_DIR, f"menubar-{name}.png")


class Bridge(NSObject):
    """Receives messages from the page and pushes JS back on the main thread."""

    def initWithApp_(self, app):
        self = objc.super(Bridge, self).init()
        self.app = app
        return self

    def userContentController_didReceiveScriptMessage_(self, _ucc, message):
        try:
            body = message.body()
            self.app.handle_message(dict(body) if body is not None else {})
        except Exception as e:
            self.app.push("error", {"message": f"bridge: {e}"})

    def pushJS_(self, js):
        wv = self.app.webview
        if wv is not None:
            wv.evaluateJavaScript_completionHandler_(js, None)

    def applyStatus_(self, status):
        self.app.apply_status(str(status))

    def showWindow_(self, _arg):
        self.app.show_window()


class WindowDelegate(NSObject):
    def windowShouldClose_(self, window):
        window.orderOut_(None)
        return False


class DuckyGuardApp(rumps.App):
    def __init__(self):
        super().__init__("DuckyGuard", icon=_icon(STATUS_PAUSED), template=False, quit_button=None)
        self.store = Store()
        self.engine = Engine(store=self.store, on_event=self.on_engine_event)
        self.simulator: Optional[BadUSBSimulator] = None
        self.window = None
        self.webview = None
        self.bridge = Bridge.alloc().initWithApp_(self)
        self.delegate_obj = WindowDelegate.alloc().init()
        self.page_ready = False
        self.update_info: Optional[dict] = None
        self._last_status = None

        self.item_status = rumps.MenuItem("Starting...")
        self.item_toggle = rumps.MenuItem("Pause protection", callback=self.menu_toggle)
        self.item_quiet = rumps.MenuItem("Quiet mode", callback=self.menu_quiet)
        self.item_quiet.state = bool(self.store.get("quiet_mode"))
        self.menu = [
            self.item_status,
            None,
            rumps.MenuItem("Open DuckyGuard", callback=self.menu_open),
            rumps.MenuItem("Test it safely", callback=self.menu_test),
            None,
            self.item_toggle,
            self.item_quiet,
            None,
            rumps.MenuItem("Quit DuckyGuard", callback=self.menu_quit),
        ]
        self.timer = rumps.Timer(self.tick, 1.0)
        self.timer.start()
        self._boot_timer = rumps.Timer(self.boot, 0.2)
        self._boot_timer.start()

    # ---------------------------------------------------------------- boot

    def boot(self, _t):
        self._boot_timer.stop()
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        if self.store.get("protection_enabled", True):
            self.engine.start()
        self.apply_status(self.engine.status)
        if (not self.store.get("onboarded") or self.engine.status in ("no_permission", "observing")
                or os.environ.get("DUCKYGUARD_SHOW_WINDOW")):
            self.show_window()
        if updates.should_check(self.store.get("last_update_check", 0), self.store.get("check_updates", False)):
            threading.Thread(target=self.check_updates, daemon=True).start()

    # -------------------------------------------------------------- window

    def ensure_window(self):
        if self.window is not None:
            return
        screen = NSScreen.mainScreen().visibleFrame() if NSScreen.mainScreen() else NSMakeRect(0, 0, 1280, 800)
        x = screen.origin.x + (screen.size.width - WINDOW_W) / 2
        y = screen.origin.y + (screen.size.height - WINDOW_H) / 2
        mask = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable |
                NSWindowStyleMaskResizable | NSWindowStyleMaskFullSizeContentView)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, WINDOW_W, WINDOW_H), mask, NSBackingStoreBuffered, False)
        win.setTitle_("DuckyGuard")
        win.setTitlebarAppearsTransparent_(True)
        win.setTitleVisibility_(1)  # hidden
        win.setMinSize_((680, 460))
        win.setReleasedWhenClosed_(False)
        win.setMovableByWindowBackground_(True)
        win.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.992, 0.984, 0.969, 1.0))
        win.setDelegate_(self.delegate_obj)
        win.setContentSize_((WINDOW_W, WINDOW_H))
        win.center()

        config = WKWebViewConfiguration.alloc().init()
        ucc = WKUserContentController.alloc().init()
        ucc.addScriptMessageHandler_name_(self.bridge, "dg")
        config.setUserContentController_(ucc)
        try:
            config.preferences().setValue_forKey_(True, "developerExtrasEnabled")
        except Exception:
            pass
        wv = WKWebView.alloc().initWithFrame_configuration_(win.contentView().bounds(), config)
        wv.setAutoresizingMask_(18)  # width | height
        try:
            wv.setValue_forKey_(False, "drawsBackground")
        except Exception:
            pass
        win.contentView().addSubview_(wv)
        index = os.path.join(UI_DIR, "index.html")
        wv.loadFileURL_allowingReadAccessToURL_(NSURL.fileURLWithPath_(index), NSURL.fileURLWithPath_(UI_DIR))
        self.window = win
        self.webview = wv

    def show_window(self):
        self.ensure_window()
        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def window_visible(self) -> bool:
        return self.window is not None and bool(self.window.isVisible())

    # --------------------------------------------------------------- bridge

    def push(self, kind: str, data) -> None:
        js = f"window.dg && dg.receive({json.dumps({'type': kind, 'data': data})});"
        self.bridge.performSelectorOnMainThread_withObject_waitUntilDone_("pushJS:", js, False)

    def push_snapshot(self) -> None:
        snap = self.engine.snapshot()
        snap["launch_at_login"] = launch_agent.is_enabled()
        snap["update"] = self.update_info
        snap["support_url"] = SUPPORT_URL
        snap["project_url"] = PROJECT_URL
        snap["data_dir"] = self.store.root
        snap["bundled"] = launch_agent.bundle_path() is not None
        self.push("snapshot", snap)

    def handle_message(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        if cmd == "ready":
            self.page_ready = True
            self.push_snapshot()
        elif cmd == "snapshot":
            self.push_snapshot()
        elif cmd == "start":
            self.engine.start()
            self.apply_status(self.engine.status)
            self.push_snapshot()
        elif cmd == "stop":
            self.engine.stop()
            self.apply_status(self.engine.status)
            self.push_snapshot()
        elif cmd == "set_setting":
            self.set_setting(msg.get("key"), msg.get("value"))
            self.push_snapshot()
        elif cmd == "trust":
            self.engine.trust_keyboard(str(msg.get("key")))
            self.push_snapshot()
        elif cmd == "untrust":
            self.engine.untrust_keyboard(str(msg.get("key")))
            self.push_snapshot()
        elif cmd == "test":
            self.run_safe_test()
        elif cmd == "export":
            self.export(str(msg.get("id")))
        elif cmd == "delete_incident":
            self.store.delete_incident(str(msg.get("id")))
            self.push_snapshot()
        elif cmd == "clear_incidents":
            self.store.clear_incidents()
            self.push_snapshot()
        elif cmd == "open_settings":
            which = msg.get("which")
            if which == "input_monitoring":
                permissions.request_input_monitoring()
                permissions.open_settings(permissions.INPUT_MONITORING_URL)
            elif which == "accessibility":
                permissions.open_settings(permissions.ACCESSIBILITY_URL)
            elif which == "login_items":
                permissions.open_settings(permissions.LOGIN_ITEMS_URL)
        elif cmd == "open_data_folder":
            subprocess.Popen(["open", self.store.root])
        elif cmd == "open_url":
            url = str(msg.get("url") or "")
            if url.startswith("https://"):
                NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
        elif cmd == "check_updates":
            threading.Thread(target=self.check_updates, daemon=True).start()
        elif cmd == "finish_onboarding":
            self.store.set("onboarded", True)
            if not self.engine.is_running():
                self.engine.start()
                self.apply_status(self.engine.status)
            self.push_snapshot()
        elif cmd == "quit":
            self.menu_quit(None)

    def set_setting(self, key: Optional[str], value) -> None:
        if key is None:
            return
        if key == "launch_at_login":
            try:
                if value:
                    launch_agent.enable()
                else:
                    launch_agent.disable()
            except Exception as e:
                self.push("toast", {"text": f"Could not change login item: {e}", "kind": "error"})
            self.store.set("launch_at_login", bool(value))
            return
        if key == "protection_enabled":
            if value:
                self.engine.start()
            else:
                self.engine.stop()
            self.apply_status(self.engine.status)
            return
        if key == "quarantine_seconds":
            try:
                value = max(0.5, min(10.0, float(value)))
            except (TypeError, ValueError):
                return
        if key == "score_software_input":
            self.engine.detector.score_software = bool(value)
        if key == "quiet_mode":
            self.item_quiet.state = bool(value)
        if key == "check_updates" and value:
            threading.Thread(target=self.check_updates, daemon=True).start()
        self.store.set(key, value)

    # ------------------------------------------------------------- actions

    def run_safe_test(self) -> None:
        if self.engine.in_test():
            return
        if not self.engine.is_running():
            self.push("toast", {"text": "Turn protection on first.", "kind": "error"})
            return
        self.show_window()
        self.push("test_begin", {"seconds": 1.2})
        self.engine.begin_test(seconds=10.0)

        def go():
            time.sleep(1.2)
            try:
                if self.simulator is None:
                    self.simulator = BadUSBSimulator()
                self.simulator.run(preset="harmless", interval_ms=12.0)
            except Exception as e:
                self.push("toast", {"text": f"Simulator failed: {e}", "kind": "error"})
            self.push("test_end", {})
        threading.Thread(target=go, daemon=True).start()

    def export(self, incident_id: str) -> None:
        inc = self.store.get_incident(incident_id)
        if not inc:
            self.push("toast", {"text": "Incident not found.", "kind": "error"})
            return
        try:
            path = export_incident(inc, self.store.exports_dir, __version__)
        except Exception as e:
            self.push("toast", {"text": f"Export failed: {e}", "kind": "error"})
            return
        subprocess.Popen(["open", "-R", path])
        self.push("toast", {"text": f"Report saved: {os.path.basename(path)}", "kind": "ok"})

    def check_updates(self) -> None:
        self.update_info = updates.check()
        self.store.set("last_update_check", time.time())
        self.push_snapshot()

    # --------------------------------------------------------------- events

    def on_engine_event(self, evt: dict) -> None:
        kind = evt.get("event")
        self.bridge.performSelectorOnMainThread_withObject_waitUntilDone_("applyStatus:", evt.get("status"), False)
        if kind == "block_started":
            if not self.store.get("quiet_mode"):
                try:
                    s = NSSound.soundNamed_("Basso")
                    if s:
                        s.play()
                except Exception:
                    pass
            self.push("block_started", {"t": evt.get("t")})
            self.push_snapshot()
        elif kind == "block_finished":
            inc = evt.get("incident") or {}
            if not self.store.get("quiet_mode") and not inc.get("simulated"):
                self.notify("Keystroke injection blocked", inc.get("summary", ""))
            self.push("block_finished", {"incident": inc})
            self.push_snapshot()
        elif kind == "keyboard_attached":
            kb = evt.get("keyboard", {})
            if not evt.get("trusted") and not kb.get("built_in"):
                if not self.store.get("quiet_mode"):
                    self.notify("New keyboard", f"{kb.get('product', 'A keyboard')} connected. Trust it in DuckyGuard > Devices if it is yours.")
                self.bridge.performSelectorOnMainThread_withObject_waitUntilDone_("showWindow:", None, False)
            self.push_snapshot()
        elif kind in ("status", "devices"):
            self.push_snapshot()

    def notify(self, title: str, text: str) -> None:
        try:
            rumps.notification(title, "", text, sound=False)
            return
        except Exception:
            pass
        safe = lambda s: s.replace('"', "'")
        try:
            subprocess.Popen(["osascript", "-e", f'display notification "{safe(text)}" with title "{safe(title)}"'])
        except Exception:
            pass

    def apply_status(self, status: str) -> None:
        if status == self._last_status:
            return
        self._last_status = status
        self.icon = _icon(status)
        labels = {
            STATUS_PROTECTED: "Protected",
            STATUS_OBSERVING: "Observing only (no Accessibility permission)",
            STATUS_PAUSED: "Paused",
            STATUS_ALERT: "Blocking a keystroke burst",
            "no_permission": "Needs permission",
            "error": "Error, open DuckyGuard",
        }
        self.item_status.title = labels.get(status, status)
        self.item_toggle.title = "Pause protection" if self.engine.is_running() else "Resume protection"

    def tick(self, _t) -> None:
        if self.page_ready and self.window_visible():
            self.push_snapshot()

    # ----------------------------------------------------------------- menu

    def menu_open(self, _s):
        self.show_window()

    def menu_test(self, _s):
        self.run_safe_test()

    def menu_toggle(self, _s):
        if self.engine.is_running():
            self.engine.stop()
        else:
            self.engine.start()
        self.apply_status(self.engine.status)

    def menu_quiet(self, sender):
        self.set_setting("quiet_mode", not bool(self.store.get("quiet_mode")))

    def menu_quit(self, _s):
        try:
            self.engine.stop(persist=False)
        finally:
            rumps.quit_application()


def run_app() -> None:
    DuckyGuardApp().run()
