"""
DuckyGuard - menu bar app.

A rumps status item (duck glyph, four states) plus one native window that
hosts the dashboard (local HTML in a WKWebView, no web server, no open port).
The page talks to Python through a WKScriptMessageHandler and Python pushes
JSON back with evaluateJavaScript. Everything stays inside this process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from typing import Optional

import objc
import rumps
from AppKit import (NSApp, NSAppearance, NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
                    NSColor, NSMakeRect, NSMenu, NSMenuItem, NSScreen, NSSound, NSToolbar, NSWindow,
                    NSWindowStyleMaskClosable, NSWindowStyleMaskFullSizeContentView, NSWindowStyleMaskMiniaturizable,
                    NSWindowStyleMaskTitled, NSWorkspace)
from Foundation import NSObject, NSURL
from WebKit import WKUserContentController, WKWebView, WKWebViewConfiguration

from . import __version__, launch_agent, permissions, updates
from .engine import (Engine, STATUS_ALERT, STATUS_ERROR, STATUS_HOLD, STATUS_NO_PERMISSION, STATUS_OBSERVING, STATUS_PAUSED,
                     STATUS_PROTECTED)
from .incidents import export_incident, export_incident_ocsf
from .simulator import BadUSBSimulator
from .store import Store

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
ICON_DIR = os.path.join(UI_DIR, "icons")
SUPPORT_URL: Optional[str] = None   # pay-what-you-want link; hidden in the UI until set
PROJECT_URL = "https://github.com/stevenhainley/DuckyGuard"

WINDOW_W, WINDOW_H = 820, 560


def _icon(state: str) -> str:
    """Protected only when keys can really be dropped. Installed-but-not-blocking gets its own glyph."""
    name = {STATUS_PROTECTED: "protected", STATUS_PAUSED: "paused", STATUS_ALERT: "alert", STATUS_HOLD: "alert",
            STATUS_OBSERVING: "attention", STATUS_NO_PERMISSION: "attention", STATUS_ERROR: "attention"}.get(state, "attention")
    path = os.path.join(ICON_DIR, f"menubar-{name}.png")
    return path if os.path.exists(path) else os.path.join(ICON_DIR, "menubar-paused.png")


def _log(what: str) -> None:
    """Errors go to stderr with their traceback; the window gets a sentence instead."""
    print(f"DuckyGuard: {what}", file=sys.stderr)
    traceback.print_exc()


def _clock(ts: float) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


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
        except Exception:
            _log("could not handle a message from the window")
            self.app.push("toast", {"text": "That did not work. Try again, or quit and reopen DuckyGuard.", "kind": "error"})

    def pushJS_(self, js):
        wv = self.app.webview
        if wv is not None:
            wv.evaluateJavaScript_completionHandler_(js, None)

    def applyStatus_(self, status):
        self.app.apply_status(str(status))

    def showWindow_(self, _arg):
        self.app.show_window()

    def engineEvent_(self, evt):
        self.app.handle_engine_event(evt)

    def openSettings_(self, _sender):
        self.app.show_window()
        self.app.push("tab", {"tab": "settings"})

    def showAbout_(self, _sender):
        NSApp.activateIgnoringOtherApps_(True)
        NSApp.orderFrontStandardAboutPanel_(None)


class WindowDelegate(NSObject):
    def windowShouldClose_(self, window):
        window.orderOut_(None)
        return False

    def windowDidBecomeKey_(self, _note):
        self.app.window_key = True

    def windowDidResignKey_(self, _note):
        self.app.window_key = False


class DuckyGuardApp(rumps.App):
    def __init__(self):
        super().__init__("DuckyGuard", icon=_icon(STATUS_PAUSED), template=True, quit_button=None)
        self.store = Store()
        self.engine = Engine(store=self.store, on_event=self.on_engine_event)
        self.simulator: Optional[BadUSBSimulator] = None
        self.window = None
        self.webview = None
        self.bridge = Bridge.alloc().initWithApp_(self)
        self.delegate_obj = WindowDelegate.alloc().init()
        self.delegate_obj.app = self
        self.window_key = False            # kept by the window delegate; the safe test types only while it is True
        self.page_ready = False
        self._queued: list = []            # messages for the page that were sent before it finished loading
        self.update_info: Optional[dict] = None
        self._last_status = None
        self._testing = False

        # No Cmd+Q anywhere, on purpose: a payload could use it to quit the guard (docs/THREAT_MODEL.md).
        self.item_status = rumps.MenuItem("Starting…")
        self.item_keep = rumps.MenuItem("Keep Keyboard Blocked", callback=self.menu_keep_blocked)
        self.item_allow = rumps.MenuItem("Allow Keyboard Once", callback=self.menu_allow_once)
        self.item_pause5 = rumps.MenuItem("Pause for 5 Minutes", callback=lambda _s: self.pause(300))
        self.item_pause60 = rumps.MenuItem("Pause for 1 Hour", callback=lambda _s: self.pause(3600))
        self.item_pause = rumps.MenuItem("Pause Until I Resume", callback=lambda _s: self.pause(None))
        self.item_resume = rumps.MenuItem("Resume Protection", callback=lambda _s: self.resume())
        self.item_quiet = rumps.MenuItem("Mute Alerts", callback=self.menu_quiet)
        self.item_quiet.state = bool(self.store.get("quiet_mode"))
        self.menu = [
            self.item_status,
            self.item_keep,
            self.item_allow,
            None,
            rumps.MenuItem("Open DuckyGuard", callback=self.menu_open),
            rumps.MenuItem("Run Safe Test", callback=self.menu_test),
            None,
            self.item_pause5,
            self.item_pause60,
            self.item_pause,
            self.item_resume,
            self.item_quiet,
            None,
            rumps.MenuItem("Settings…", callback=lambda _s: self.bridge.openSettings_(None), key=","),
            rumps.MenuItem("About DuckyGuard", callback=lambda _s: self.bridge.showAbout_(None)),
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
        self.install_main_menu()
        if self.store.get("protection_enabled", True):
            self.engine.start()
        self.apply_status(self.engine.status)
        if (not self.store.get("onboarded") or self.engine.status in ("no_permission", "observing")
                or os.environ.get("DUCKYGUARD_SHOW_WINDOW")):
            self.show_window()
        if os.environ.get("DUCKYGUARD_AUTOTEST"):       # for screenshots and release checks: run the safe test once after launch
            self._autotest = rumps.Timer(self._run_autotest, 3.5)
            self._autotest.start()
        if updates.should_check(self.store.get("last_update_check", 0), self.store.get("check_updates", False)):
            threading.Thread(target=self.check_updates, daemon=True).start()

    def _run_autotest(self, timer):
        if not getattr(self, "_autotest_armed", False):      # a rumps timer fires once straight away; wait for the next tick
            self._autotest_armed = True
            return
        timer.stop()
        self.run_safe_test()

    def install_main_menu(self):
        """A menu bar app still needs a main menu: it is what makes Cmd+W, Cmd+M, Cmd+C, Cmd+A and Cmd+, work
        while the window is in front."""
        main = NSMenu.alloc().init()

        def submenu(title, items):
            top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
            menu = NSMenu.alloc().initWithTitle_(title)
            for it in items:
                if it is None:
                    menu.addItem_(NSMenuItem.separatorItem())
                    continue
                label, action, key, target = it
                mi = menu.addItemWithTitle_action_keyEquivalent_(label, action, key)
                if target is not None:
                    mi.setTarget_(target)
            top.setSubmenu_(menu)
            main.addItem_(top)

        submenu("DuckyGuard", [("About DuckyGuard", "showAbout:", "", self.bridge), None,
                               ("Settings…", "openSettings:", ",", self.bridge), None,
                               ("Hide DuckyGuard", "hide:", "h", None)])
        submenu("Edit", [("Copy", "copy:", "c", None), ("Select All", "selectAll:", "a", None)])
        submenu("Window", [("Close", "performClose:", "w", None), ("Minimize", "performMiniaturize:", "m", None)])
        NSApp.setMainMenu_(main)

    # -------------------------------------------------------------- window

    def ensure_window(self):
        if self.window is not None:
            return
        screen = NSScreen.mainScreen().visibleFrame() if NSScreen.mainScreen() else NSMakeRect(0, 0, 1280, 800)
        x = screen.origin.x + (screen.size.width - WINDOW_W) / 2
        y = screen.origin.y + (screen.size.height - WINDOW_H) / 2
        # Fixed size: the dashboard is one composed screen, not a document.
        mask = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable |
                NSWindowStyleMaskFullSizeContentView)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, WINDOW_W, WINDOW_H), mask, NSBackingStoreBuffered, False)
        win.setTitle_("DuckyGuard")
        win.setTitlebarAppearsTransparent_(True)
        win.setTitleVisibility_(1)  # hidden
        win.setReleasedWhenClosed_(False)
        try:
            win.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))   # the page is dark only
            toolbar = NSToolbar.alloc().initWithIdentifier_("main")       # empty: it only makes the title bar 52 pt tall,
            toolbar.setShowsBaselineSeparator_(False)                      # so the traffic lights centre on the page's nav
            win.setToolbar_(toolbar)
            win.setToolbarStyle_(3)                                        # NSWindowToolbarStyleUnified
        except Exception:
            _log("could not style the window")
        win.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(0.032, 0.047, 0.110, 1.0))   # --color-paper
        win.setDelegate_(self.delegate_obj)
        win.setContentSize_((WINDOW_W, WINDOW_H))
        win.center()

        config = WKWebViewConfiguration.alloc().init()
        ucc = WKUserContentController.alloc().init()
        ucc.addScriptMessageHandler_name_(self.bridge, "dg")
        config.setUserContentController_(ucc)
        if os.environ.get("DUCKYGUARD_DEV"):            # Inspect Element only for development
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
        if not self.page_ready and kind != "snapshot":      # the page is still loading: keep it for when it says "ready"
            self._queued.append((kind, data))
            return
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
            queued, self._queued = self._queued, []
            for kind, data in queued:
                self.push(kind, data)
        elif cmd == "snapshot":
            self.push_snapshot()
        elif cmd == "log":                               # an error on the page; keep it where a bug report can find it
            print(f"DuckyGuard page: {str(msg.get('text'))[:2000]}", file=sys.stderr, flush=True)
        elif cmd in ("start", "resume"):
            self.resume()
        elif cmd == "stop":
            self.pause(None)
        elif cmd == "pause":
            secs = msg.get("seconds")
            self.pause(None if secs is None else max(10.0, min(24 * 3600.0, float(secs))))
        elif cmd == "restart":                           # after an error: rebuild the tap
            self.engine.stop(persist=False)
            self.engine.start()
            self.refresh_menu()
            self.push_snapshot()
        elif cmd == "drag":                              # mouse went down on the page's nav: move the window
            ev = NSApp.currentEvent()
            if self.window is not None and ev is not None:
                self.window.performWindowDragWithEvent_(ev)
        elif cmd == "set_setting":
            self.set_setting(msg.get("key"), msg.get("value"))
            self.push_snapshot()
        elif cmd == "trust":
            self.engine.trust_keyboard(str(msg.get("key")))
            self.push_snapshot()
        elif cmd == "untrust":
            self.engine.untrust_keyboard(str(msg.get("key")))
            self.push_snapshot()
        elif cmd == "allow_keyboard":
            self.engine.allow_keyboard(str(msg.get("key")), trust=bool(msg.get("trust", True)))
            self.push_snapshot()
        elif cmd == "block_keyboard":
            self.engine.block_keyboard(str(msg.get("key")))
            self.push_snapshot()
        elif cmd == "test":
            self.run_safe_test()
        elif cmd == "export":
            self.export(str(msg.get("id")))
        elif cmd == "export_ocsf":
            self.export(str(msg.get("id")), ocsf=True)
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
                permissions.request_accessibility()
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
            self.engine.trust_connected(msg.get("trust") or [])
            if not self.engine.is_running():
                self.engine.start()
            self.refresh_menu()
            self.push_snapshot()
        elif cmd == "quit":
            self.menu_quit(None)

    def set_setting(self, key: Optional[str], value) -> None:
        if key is None:
            return
        if key == "launch_at_login":
            try:
                if value:
                    launch_agent.enable(keep_alive=bool(self.engine.store.get("keep_alive", False)))
                else:
                    launch_agent.disable()
            except Exception:
                _log("could not change the login item")
                self.push("toast", {"text": "Could not change the login item. Try again from System Settings › General › Login Items.", "kind": "error"})
            self.store.set("launch_at_login", bool(value))
            return
        if key == "protection_enabled":
            self.resume() if value else self.pause(None)
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
        if key == "keep_alive" and launch_agent.is_enabled():
            try:
                launch_agent.enable(keep_alive=bool(value))
            except Exception:
                _log("could not update the login item")
                self.push("toast", {"text": "Could not update the login item.", "kind": "error"})
        if key == "hold_seconds":
            try:
                value = max(5.0, min(120.0, float(value)))
            except (TypeError, ValueError):
                return
        if key == "check_updates" and value:
            threading.Thread(target=self.check_updates, daemon=True).start()
        self.store.set(key, value)

    # ------------------------------------------------------------- actions

    def pause(self, seconds: Optional[float]) -> None:
        self.engine.pause(seconds)
        self.refresh_menu()
        self.push_snapshot()

    def resume(self) -> None:
        self.engine.paused_until = None
        self.engine.start()
        self.refresh_menu()
        self.push_snapshot()

    def run_safe_test(self) -> None:
        """Types one harmless sentence at injector speed into DuckyGuard's own window. The keys are posted
        system-wide, so it types only while this window is the key window and stops the moment it is not."""
        if self._testing or self.engine.in_test():
            return
        if not self.engine.is_running():
            self.push("toast", {"text": "Resume protection first, then run the safe test.", "kind": "error"})
            return
        self._testing = True
        self.show_window()
        self.push("test_begin", {"seconds": 1.2})
        self.engine.begin_test(seconds=10.0)

        def go():
            time.sleep(1.2)
            completed = False
            try:
                if self.window_key:
                    if self.simulator is None:
                        self.simulator = BadUSBSimulator()
                    completed = self.simulator.run(preset="harmless", interval_ms=12.0, keep_going=lambda: self.window_key)
                if not completed:
                    self.push("toast", {"text": "Test stopped: DuckyGuard's window was not in front. Click the window and run it again.", "kind": "error"})
            except Exception:
                _log("the safe test could not type")
                self.push("toast", {"text": "The safe test could not type. Check that Accessibility is on for DuckyGuard.", "kind": "error"})
            self._testing = False
            self.push("test_end", {"completed": completed})
        threading.Thread(target=go, daemon=True).start()

    def export(self, incident_id: str, ocsf: bool = False) -> None:
        inc = self.store.get_incident(incident_id)
        if not inc:
            self.push("toast", {"text": "Incident not found.", "kind": "error"})
            return
        try:
            path = (export_incident_ocsf if ocsf else export_incident)(inc, self.store.exports_dir, __version__)
        except Exception:
            _log("could not export the incident")
            self.push("toast", {"text": "Could not save the report. Check that the data folder is writable.", "kind": "error"})
            return
        subprocess.Popen(["open", "-R", path])
        self.push("toast", {"text": f"Report saved: {os.path.basename(path)}", "kind": "ok"})

    def check_updates(self) -> None:
        self.update_info = updates.check()
        self.store.set("last_update_check", time.time())
        self.push_snapshot()

    # --------------------------------------------------------------- events

    def on_engine_event(self, evt: dict) -> None:
        """Called on whatever thread the engine is on, including the keyboard tap. It only hands the event to
        the main thread; sounds, notifications and snapshots never run inside the tap."""
        self.bridge.performSelectorOnMainThread_withObject_waitUntilDone_("engineEvent:", evt, False)

    def handle_engine_event(self, evt) -> None:
        kind, quiet = evt.get("event"), bool(self.store.get("quiet_mode"))
        self.refresh_menu()
        if kind == "block_started":
            if not quiet:
                try:
                    s = NSSound.soundNamed_("Basso")
                    if s:
                        s.play()
                except Exception:
                    pass
            self.push("block_started", {"t": evt.get("t")})
        elif kind == "block_finished":
            inc = evt.get("incident") or {}
            if not quiet and not inc.get("simulated"):
                blocked, through = inc.get("blocked_count", 0), inc.get("keys_before_block", 0)
                self.notify("Scripted Typing Blocked", f"{blocked} keys blocked, {through} got through. Unplug the device.")
            self.push("block_finished", {"incident": inc})
        elif kind == "keyboard_attached":
            kb = evt.get("keyboard", {})
            # A held keyboard gets its one notification from hold_started; this is the no-hold case.
            if not evt.get("trusted") and not kb.get("built_in") and not evt.get("held") and not quiet:
                self.notify("New Keyboard Connected", f"{kb.get('product') or 'A keyboard'} is not trusted. Fast scripted typing from it is still blocked.")
        elif kind == "hold_started":
            kb = evt.get("keyboard", {})
            if not quiet:
                self.notify("New Keyboard on Hold", f"{kb.get('product') or 'A keyboard'} was just plugged in. Its keys are blocked, and so are your own keyboard's, until you choose in DuckyGuard. Use the trackpad or mouse.")
            self.show_window()
        elif kind == "hold_ended":
            if evt.get("result") == "expired" and not quiet:
                kb = evt.get("keyboard", {})
                self.notify("Hold Ended", f"Nobody chose, so the hold on {kb.get('product') or 'the keyboard'} ended. It is still untrusted, and fast scripted typing is still blocked.")
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

    def status_line(self) -> str:
        """The first line of the menu: the same words the window uses."""
        e, perms = self.engine, permissions.status()
        hold = e._hold or {}
        name = (hold.get("keyboard") or {}).get("product") or "New keyboard"
        if e.status == STATUS_PAUSED:
            return f"Paused until {_clock(e.paused_until)}" if e.paused_until else "Paused"
        if e.status == STATUS_PROTECTED and not e.dropping():
            return "Recording only: nothing is blocked"
        return {
            STATUS_PROTECTED: "Protected",
            STATUS_HOLD: f"{name} on hold",
            STATUS_ALERT: "Blocking scripted typing",
            STATUS_OBSERVING: "Can't block: Accessibility is off",
            STATUS_NO_PERMISSION: "Not protected: Input Monitoring is off" if not perms["can_observe"] else "Not protected: open DuckyGuard",
            STATUS_ERROR: "Not protected: open DuckyGuard",
        }.get(e.status, "Not protected: open DuckyGuard")

    def apply_status(self, status: str) -> None:
        self.refresh_menu()

    def refresh_menu(self) -> None:
        e = self.engine
        shown = STATUS_OBSERVING if (e.status == STATUS_PROTECTED and not e.dropping()) else e.status    # record only is not protected
        if shown != self._last_status:
            self._last_status = shown
            self.icon = _icon(shown)
        self.item_status.title = self.status_line()
        hold = e._hold
        name = ((hold or {}).get("keyboard") or {}).get("product") or "Keyboard"
        self.item_keep.title, self.item_allow.title = f"Keep “{name}” Blocked", f"Allow “{name}” Once"
        paused = e.status == STATUS_PAUSED
        for item, hidden in ((self.item_keep, hold is None or bool(hold.get("blocked"))), (self.item_allow, hold is None),
                             (self.item_pause5, paused), (self.item_pause60, paused), (self.item_pause, paused), (self.item_resume, not paused)):
            item._menuitem.setHidden_(hidden)

    def tick(self, _t) -> None:
        changed = self.engine.resume_if_due()
        try:
            changed = self.engine.refresh_permissions() or changed      # a permission granted after launch takes effect here
        except Exception:
            _log("could not re-check permissions")
        self.refresh_menu()
        if self.page_ready and (changed or self.window_visible()):
            self.push_snapshot()

    # ----------------------------------------------------------------- menu

    def menu_open(self, _s):
        self.show_window()

    def menu_test(self, _s):
        self.run_safe_test()

    def menu_keep_blocked(self, _s):
        hold = self.engine._hold
        if hold:
            self.engine.block_keyboard(hold["key"])
            self.refresh_menu()
            self.push_snapshot()

    def menu_allow_once(self, _s):
        hold = self.engine._hold
        if hold:
            self.engine.allow_keyboard(hold["key"], trust=False)
            self.refresh_menu()
            self.push_snapshot()

    def menu_quiet(self, sender):
        self.set_setting("quiet_mode", not bool(self.store.get("quiet_mode")))

    def menu_quit(self, _s):
        try:
            self.engine.stop(persist=False)
        finally:
            rumps.quit_application()


def run_app() -> None:
    DuckyGuardApp().run()
