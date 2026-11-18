"""Listen-only key timing capture for hardware tests. Records time, down/up and key for N seconds.
usage: capture.py <out.jsonl> <seconds>"""
import json, sys, time
from pynput import keyboard
out, secs = sys.argv[1], float(sys.argv[2]); f = open(out, "w")
def rec(kind):
    def cb(key, injected=False):
        k = getattr(key, "char", None) or str(key)
        f.write(json.dumps({"t": time.time(), "e": kind, "k": k, "sw": bool(injected)}) + "\n"); f.flush()
    return cb
with keyboard.Listener(on_press=rec("d"), on_release=rec("u")) as l:
    time.sleep(secs); l.stop()
