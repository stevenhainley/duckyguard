"""Minimal Flipper Zero CLI client. usage: flip.py "<command>" [timeout]"""
import sys, time, glob, serial
def port():
    p = glob.glob("/dev/cu.usbmodemflip_*")
    if not p: raise SystemExit("flipper serial port not found")
    return p[0]
def run(cmd, timeout=6.0, s=None):
    own = s is None
    if own:
        s = serial.Serial(port(), 230400, timeout=0.2); time.sleep(0.3); s.reset_input_buffer()
        s.write(b"\r\n"); time.sleep(0.3); s.read(65536)
    s.write(cmd.encode() + b"\r\n"); buf = b""; t0 = time.time()
    while time.time() - t0 < timeout:
        chunk = s.read(4096); buf += chunk
        if buf.rstrip().endswith(b">:"): break
    if own: s.close()
    out = buf.decode("utf-8", "replace")
    return out.split("\n", 1)[1] if "\n" in out else out
if __name__ == "__main__":
    print(run(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 6.0))
