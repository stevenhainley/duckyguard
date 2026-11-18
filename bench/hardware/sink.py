"""Harmless text sink for hardware tests: a focused window that records whatever is typed into it.
usage: sink.py <out.json> <seconds>"""
import json, sys, time
import objc
from AppKit import (NSApplication, NSApp, NSWindow, NSTextView, NSScrollView, NSMakeRect, NSBackingStoreBuffered,
                    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable, NSApplicationActivationPolicyRegular, NSFont, NSTimer)
from Foundation import NSObject

out, secs = sys.argv[1], float(sys.argv[2])

class Ticker(NSObject):
    def init(self):
        self = objc.super(Ticker, self).init(); self.t0 = time.time(); self.samples = []; self.last = None; return self
    def tick_(self, _):
        txt = str(tv.string())
        if txt != self.last:
            self.samples.append({"t": round(time.time() - self.t0, 4), "len": len(txt)}); self.last = txt
        if time.time() - self.t0 > secs:
            json.dump({"text": txt, "chars": len(txt), "samples": self.samples}, open(out, "w"), indent=1)
            NSApp.terminate_(None)

app = NSApplication.sharedApplication(); app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(NSMakeRect(200, 300, 760, 320),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable, NSBackingStoreBuffered, False)
win.setTitle_("DuckyGuard hardware test sink: do not type here")
sv = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, 760, 320))
tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 760, 320)); tv.setFont_(NSFont.userFixedPitchFontOfSize_(13))
tv.setAutomaticQuoteSubstitutionEnabled_(False); tv.setAutomaticDashSubstitutionEnabled_(False)
tv.setAutomaticTextReplacementEnabled_(False); tv.setAutomaticSpellingCorrectionEnabled_(False)
sv.setDocumentView_(tv); win.setContentView_(sv); win.makeKeyAndOrderFront_(None); win.makeFirstResponder_(tv)
app.activateIgnoringOtherApps_(True)
tk = Ticker.alloc().init()
NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.02, tk, "tick:", None, True)
app.run()
