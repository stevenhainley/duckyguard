"""COMPAT ONLY: the v1.0 server, kept so the already-installed v1 app wrapper (python3 -m duckyguard.server)
keeps launching after v2 became main. v1 code lives in duckyguard/_v1. Not part of v2 features; remove once v1 is retired."""
"""
DuckyGuard - Local API & Web Server
Serves the modern light creme-orange desktop interface and provides
JSON APIs for live telemetry, simulation triggering, and incident triage.
"""

import glob
import http.server
import json
import os
import subprocess
import threading
import time
import urllib.parse
from typing import Optional

from ._v1.engine import DuckyGuardEngine
from ._v1.simulator import BadUSBSimulator


class DuckyGuardServer:
    """Embedded localhost HTTP server and API handler for DuckyGuard."""

    PORT = 4848

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.web_dir = os.path.join(os.path.dirname(__file__), "_v1", "web")
        self.reports_dir = os.path.join(self.base_dir, "reports")
        self.captures_dir = os.path.join(self.base_dir, "captures")
        self.assets_dir = os.path.join(self.base_dir, "assets")

        self.engine = DuckyGuardEngine(base_dir=self.base_dir)
        self.simulator = BadUSBSimulator()

        self.httpd: Optional[http.server.HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self, blocking: bool = False):
        """Starts the engine and web server."""
        # Start core protection engine
        threading.Thread(target=self.engine.start, kwargs={"blocking": False}, daemon=True).start()

        server_ref = self

        class RequestHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=server_ref.web_dir, **kwargs)

            def log_message(self, format, *args):
                pass  # Silence terminal access logs

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path

                if path == "/api/status":
                    self._handle_status()
                elif path == "/api/incidents":
                    self._handle_incidents()
                elif path == "/api/incident":
                    qs = urllib.parse.parse_qs(parsed.query)
                    fname = qs.get("file", [""])[0]
                    self._handle_incident_detail(fname)
                elif path.startswith("/assets/"):
                    asset_name = path[len("/assets/"):]
                    mime = "image/png"
                    if asset_name.endswith(".jpg") or asset_name.endswith(".jpeg"):
                        mime = "image/jpeg"
                    elif asset_name.endswith(".svg"):
                        mime = "image/svg+xml"
                    self._serve_asset(asset_name, mime)
                else:
                    super().do_GET()

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path

                if path == "/api/toggle":
                    self._handle_toggle()
                elif path == "/api/simulate":
                    content_len = int(self.headers.get("Content-Length", 0))
                    post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
                    self._handle_simulate(post_body)
                elif path == "/api/open-folder":
                    subprocess.run(["open", server_ref.reports_dir])
                    self._send_json({"status": "ok"})
                elif path == "/api/biometric-test":
                    content_len = int(self.headers.get("Content-Length", 0))
                    post_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
                    try:
                        data = json.loads(post_body)
                        char = data.get("char", "a")
                        ts = data.get("timestamp", time.time())
                        is_ano, conf, met = server_ref.engine.detector.record_keystroke(char, timestamp=ts)
                        self._send_json({"is_anomaly": is_ano, "confidence": conf, "metrics": met})
                    except Exception as e:
                        self._send_json({"error": str(e)})
                else:
                    self.send_error(404, "Not Found")

            def _handle_status(self):
                keys = server_ref.engine.detector.total_keys_inspected
                attacks = server_ref.engine.detector.anomalies_detected
                running = server_ref.engine._running

                devices_raw = server_ref.engine.usb_watcher._get_current_hid_devices()
                devices = []
                for d in sorted(devices_raw):
                    parts = d.split(":", 2)
                    devices.append({
                        "vendor_id": parts[0] if len(parts) > 0 else "N/A",
                        "product_id": parts[1] if len(parts) > 1 else "N/A",
                        "name": parts[2] if len(parts) > 2 else "Unknown HID",
                    })

                resp = {
                    "running": running,
                    "keys_inspected": keys,
                    "attacks_neutralized": attacks,
                    "active_devices": len(devices),
                    "devices": devices,
                    "last_incident": server_ref.engine.last_incident_summary,
                    "telemetry": list(server_ref.engine.detector.recent_events),
                }
                self._send_json(resp)

            def _handle_incidents(self):
                reports = sorted(glob.glob(os.path.join(server_ref.reports_dir, "incident-*.md")), reverse=True)
                out = []
                for r in reports:
                    fname = os.path.basename(r)
                    stat = os.stat(r)
                    out.append({
                        "filename": fname,
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                        "size": stat.st_size,
                    })
                self._send_json({"incidents": out})

            def _handle_incident_detail(self, filename: str):
                safe_name = os.path.basename(filename)
                fpath = os.path.join(server_ref.reports_dir, safe_name)
                if not os.path.exists(fpath):
                    self.send_error(404, "Report not found")
                    return
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()

                # Look for matching YARA rule
                yara_name = safe_name.replace("incident-", "rule-").replace(".md", ".yar")
                yara_path = os.path.join(server_ref.reports_dir, yara_name)
                yara_content = ""
                if os.path.exists(yara_path):
                    with open(yara_path, "r", encoding="utf-8") as yf:
                        yara_content = yf.read()

                self._send_json({"content": content, "yara": yara_content})

            def _handle_toggle(self):
                if server_ref.engine._running:
                    server_ref.engine.stop()
                else:
                    threading.Thread(target=server_ref.engine.start, kwargs={"blocking": False}, daemon=True).start()
                self._send_json({"running": server_ref.engine._running})

            def _handle_simulate(self, body_str: str):
                try:
                    payload = json.loads(body_str)
                except Exception:
                    payload = {}
                preset = payload.get("preset", "resume_dropper")
                is_badusb = payload.get("is_badusb", True)

                threading.Thread(
                    target=server_ref.simulator.run_simulation,
                    kwargs={"preset_name": preset, "is_badusb": is_badusb, "initial_countdown_sec": 2},
                    daemon=True,
                ).start()
                self._send_json({"status": "fired", "preset": preset, "is_badusb": is_badusb})

            def _serve_asset(self, filename: str, mime: str):
                p = os.path.join(server_ref.assets_dir, filename)
                if not os.path.exists(p):
                    self.send_error(404, "Asset not found")
                    return
                with open(p, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_json(self, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.PORT), RequestHandler)
        print(f"[*] DuckyGuard UI & API Server listening at http://127.0.0.1:{self.PORT}")

        if blocking:
            self.httpd.serve_forever()
        else:
            self._server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._server_thread.start()


def run_server():
    server = DuckyGuardServer()
    server.start(blocking=True)


if __name__ == "__main__":
    run_server()
