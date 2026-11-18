"""Hardware test harness: push a JS BadUSB payload to the Flipper, run it into the sink, collect results.
usage: harness.py <label> <per_char_delay_ms|jitter> [vid pid]"""
import json, os, subprocess, sys, time, glob, serial
HERE = os.path.dirname(os.path.abspath(__file__)); V = sys.executable
TEXT = "DGTEST the quick brown fox jumps over the lazy dog 0123456789 " * 2
def port():
    for _ in range(100):
        p = glob.glob("/dev/cu.usbmodemflip_*")
        if p: return p[0]
        time.sleep(0.2)
    raise SystemExit("flipper serial port did not come back")
def open_cli():
    s = serial.Serial(port(), 230400, timeout=0.3); time.sleep(0.4); s.write(b"\r\n"); time.sleep(0.4); s.read(65536); return s
def cmd(s, c, timeout=5.0):
    s.write(c.encode() + b"\r\n"); buf = b""; t0 = time.time()
    while time.time() - t0 < timeout:
        buf += s.read(4096)
        if buf.rstrip().endswith(b">:"): break
    return buf.decode("utf-8", "replace")
def write_file(s, path, data: bytes):
    cmd(s, f"storage remove {path}")
    s.write(f"storage write_chunk {path} {len(data)}\r\n".encode()); time.sleep(0.4); s.read(4096)
    s.write(data); time.sleep(0.6); return s.read(4096).decode("utf-8", "replace")
def js_payload(mode, vid=None, pid=None):
    ident = f'vid: {vid}, pid: {pid}, mfrName: "DGTest", prodName: "DG Test Keyboard", ' if vid else 'vid: 0x046D, pid: 0xC529, mfrName: "Flipper Devices Inc.", prodName: "Flipper Zero", '
    head = f'let badusb = require("badusb");\nbadusb.setup({{ {ident}layoutPath: "/ext/badusb/assets/layouts/en-US.kl" }});\n' \
           'let n = 0;\nwhile (!badusb.isConnected() && n < 150) { delay(100); n++; }\ndelay(' + os.environ.get('PREDELAY_MS', '3500') + ');\n'
    if mode == "jitter":
        body = 'let math = require("math");\nlet t = "' + TEXT + '";\nfor (let i = 0; i < t.length; i++) { badusb.print(t.slice(i, i + 1)); delay(60 + math.floor(math.random() * 80)); }\n'
    else:
        body = f'badusb.print("{TEXT}", {int(mode)});\n' if int(mode) > 0 else f'badusb.print("{TEXT}");\n'
    return (head + body + "delay(500);\nbadusb.quit();\n").encode()
def front():
    return subprocess.run("lsappinfo info -only name $(lsappinfo front)", shell=True, capture_output=True, text=True).stdout
def main():
    label, mode = sys.argv[1], sys.argv[2]; vid, pid = (sys.argv[3], sys.argv[4]) if len(sys.argv) > 4 else (None, None)
    dur = float(os.environ.get("DUR", 0)) or (int(os.environ.get("PREDELAY_MS", "3500")) - 3500) / 1000 + {"jitter": 28, "100": 26, "50": 20}.get(mode, 16)
    s = open_cli(); cmd(s, "loader close"); time.sleep(0.5); cmd(s, "storage mkdir /ext/apps/Scripts/dg"); path = "/ext/apps/Scripts/dg/t.js"
    w = write_file(s, path, js_payload(mode, vid, pid))
    logp = os.path.join(HERE, "engine.log"); log0 = os.path.getsize(logp) if os.path.exists(logp) else 0
    sink = subprocess.Popen([V, os.path.join(HERE, "sink.py"), os.path.join(HERE, f"{label}.sink.json"), str(dur)], stderr=subprocess.DEVNULL)
    time.sleep(1.8)
    if "ython" not in front(): sink.kill(); raise SystemExit("sink not frontmost; aborted before typing: " + front())
    cap = subprocess.Popen([V, os.path.join(HERE, "capture.py"), os.path.join(HERE, f"{label}.cap.jsonl"), str(dur - 2.5)], stderr=subprocess.DEVNULL)
    time.sleep(0.5); t_launch = time.time(); s.write(f"loader open /ext/apps/assets/js_app.fap {path}\r\n".encode()); time.sleep(0.8)
    try: early = s.read(4096).decode("utf-8", "replace")
    except Exception: early = "(serial dropped)"
    try: s.close()
    except Exception: pass
    sink.wait(); cap.wait()
    d = json.load(open(os.path.join(HERE, f"{label}.sink.json")))
    ev = [json.loads(x) for x in open(os.path.join(HERE, f"{label}.cap.jsonl"))]
    downs = [e for e in ev if e["e"] == "d" and len(e["k"]) == 1]; hw = [e for e in downs if not e["sw"]]
    gaps = [round((b["t"] - a["t"]) * 1000, 2) for a, b in zip(hw, hw[1:])]
    holds = []; pend = {}
    for e in ev:
        if e["e"] == "d": pend[e["k"]] = e["t"]
        elif e["k"] in pend: holds.append(round((e["t"] - pend.pop(e["k"])) * 1000, 2))
    g = sorted(gaps); med = g[len(g) // 2] if g else None
    mean = sum(gaps) / len(gaps) if gaps else 0; cv = (sum((x - mean) ** 2 for x in gaps) / len(gaps)) ** 0.5 / mean if gaps and mean else None
    eng = [json.loads(l) for l in open(logp).read()[log0:].splitlines() if l.startswith("{")] if os.path.exists(logp) else []
    res = {"label": label, "mode": mode, "sent_chars": len(TEXT), "sink_chars": d["chars"], "sink_text": d["text"],
           "captured_keydowns_hw": len(hw), "captured_sw": len(downs) - len(hw),
           "gap_ms_median": med, "gap_ms_min": g[0] if g else None, "gap_ms_max_p95": g[int(len(g) * 0.95)] if g else None, "gap_cv": round(cv, 3) if cv else None,
           "hold_ms_median": sorted(holds)[len(holds) // 2] if holds else None,
           "first_key_after_launch_s": round(hw[0]["t"] - t_launch, 2) if hw else None,
           "engine_events": [{k: e[k] for k in e if k in ("event", "status", "rule", "reason", "summary", "keys_before", "dropped", "trusted")} | ({"kb": e["keyboard"].get("product")} if "keyboard" in e else {}) for e in eng],
           "engine_raw": eng, "write": w.strip()[-60:], "js_early": early.strip()[-200:]}
    json.dump(res, open(os.path.join(HERE, f"{label}.result.json"), "w"), indent=1)
    show = {k: v for k, v in res.items() if k not in ("engine_raw", "sink_text")}; show["sink_text"] = res["sink_text"][:140]
    print(json.dumps(show, indent=1)); port()
if __name__ == "__main__": main()
