"""
DuckyGuard - Automated Threat Intelligence & Forensic Analyzer
Parses intercepted BadUSB keystroke payloads, decodes obfuscated blobs,
extracts Indicators of Compromise (IOCs), maps to MITRE ATT&CK,
and generates real-time incident reports and YARA signatures.
"""

import base64
import datetime
import os
import re
from typing import Dict, List, Optional, Tuple


class ForensicThreatAnalyzer:
    """
    Automated incident responder for intercepted HID injection attacks.
    """

    IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    URL_PATTERN = re.compile(r"https?://[^\s'\"<>\)]+", re.IGNORECASE)
    DOMAIN_PATTERN = re.compile(r"(?:https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", re.IGNORECASE)
    BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")

    MITRE_MAP = {
        "input_injection": ("T1674", "Input Injection", "Keystrokes typed by a device emulating a keyboard, at a speed or regularity no hand produces"),
        "hardware": ("T1200", "Hardware Additions", "Physical HID emulation device inserted (BadUSB/Rubber Ducky)"),
        "shell": ("T1059.004", "Command and Scripting Interpreter: Unix Shell", "Attempted execution of bash/zsh/sh commands"),
        "powershell": ("T1059.001", "Command and Scripting Interpreter: PowerShell", "Windows PowerShell script injection"),
        "applescript": ("T1059.002", "Command and Scripting Interpreter: AppleScript", "macOS osascript automated execution"),
        "ingress": ("T1105", "Ingress Tool Transfer", "Automated remote payload retrieval (curl/wget/certutil)"),
        "obfuscation": ("T1027", "Obfuscated Files or Information", "Base64 or encoded command payload detected"),
        "c2": ("T1071.001", "Application Layer Protocol: Web Protocols", "HTTP/HTTPS communication to external C2 infrastructure"),
        "persistence": ("T1547.011", "Boot or Logon Autostart Execution: Plist Modification", "macOS LaunchAgent/LaunchDaemon persistence"),
    }

    def __init__(self, reports_dir: str):
        self.reports_dir = reports_dir
        os.makedirs(self.reports_dir, exist_ok=True)

    def analyze_capture(self, capture_file_path: str, telemetry: Optional[dict] = None) -> Tuple[str, str, Dict]:
        """
        Performs full forensic triage on a captured payload file.
        Returns:
            report_path (str): Path to generated Markdown incident report.
            yara_path (str): Path to generated YARA detection rule.
            summary (dict): High-level triage metrics.
        """
        telemetry = telemetry or {}

        with open(capture_file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_payload = f.read()

        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        clean_text = raw_payload.replace("[BKSP]", "").replace("[space]", " ")

        # 1. Extract IOCs
        urls = list(set(self.URL_PATTERN.findall(clean_text)))
        ips = list(set([ip for ip in self.IP_PATTERN.findall(clean_text) if not ip.startswith("127.")]))

        # Extract domains from URLs
        domains = set()
        for u in urls:
            m = re.search(r"https?://([^/:\s]+)", u)
            if m:
                domains.add(m.group(1))

        # 2. De-obfuscate Base64
        decoded_blobs = []
        for candidate in self.BASE64_PATTERN.findall(clean_text):
            try:
                decoded_bytes = base64.b64decode(candidate)
                decoded_str = decoded_bytes.decode("utf-8", errors="ignore")
                # If decoded text looks like printable code/script
                if any(kw in decoded_str.lower() for kw in ["http", "curl", "exec", "sh", "invoke", "powershell"]):
                    decoded_blobs.append({"encoded": candidate[:30] + "...", "decoded": decoded_str})
                    # Re-scan decoded text for URLs/IPs
                    urls.extend(self.URL_PATTERN.findall(decoded_str))
            except Exception:
                pass

        urls = sorted(list(set(urls)))

        # 3. MITRE ATT&CK Classification
        techniques = [self.MITRE_MAP["hardware"]]
        if re.search(r"\b(curl|wget|certutil|Invoke-WebRequest)\b", clean_text, re.IGNORECASE):
            techniques.append(self.MITRE_MAP["ingress"])
        if re.search(r"\b(bash|zsh|sh|chmod|chown)\b", clean_text, re.IGNORECASE):
            techniques.append(self.MITRE_MAP["shell"])
        if re.search(r"\b(powershell|cmd\.exe|Invoke-Expression)\b", clean_text, re.IGNORECASE):
            techniques.append(self.MITRE_MAP["powershell"])
        if "osascript" in clean_text.lower():
            techniques.append(self.MITRE_MAP["applescript"])
        if decoded_blobs or "-enc" in clean_text.lower():
            techniques.append(self.MITRE_MAP["obfuscation"])
        if urls or ips:
            techniques.append(self.MITRE_MAP["c2"])
        if "launchagents" in clean_text.lower() or "crontab" in clean_text.lower():
            techniques.append(self.MITRE_MAP["persistence"])

        # 4. Generate Markdown Incident Report
        report_filename = f"incident-{timestamp}.md"
        report_path = os.path.join(self.reports_dir, report_filename)

        report_content = self._render_incident_report(
            timestamp=timestamp,
            raw_payload=raw_payload,
            clean_text=clean_text,
            urls=urls,
            ips=ips,
            domains=list(domains),
            decoded_blobs=decoded_blobs,
            techniques=techniques,
            telemetry=telemetry,
        )

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        # 5. Synthesize YARA Detection Rule
        yara_filename = f"rule-{timestamp}.yar"
        yara_path = os.path.join(self.reports_dir, yara_filename)
        yara_content = self._generate_yara_rule(timestamp, clean_text, urls, ips)

        with open(yara_path, "w", encoding="utf-8") as f:
            f.write(yara_content)

        summary = {
            "timestamp": timestamp,
            "urls_detected": len(urls),
            "ips_detected": len(ips),
            "mitre_techniques": len(techniques),
            "decoded_blobs": len(decoded_blobs),
            "report_path": report_path,
            "yara_path": yara_path,
        }

        return report_path, yara_path, summary

    def _render_incident_report(
        self,
        timestamp: str,
        raw_payload: str,
        clean_text: str,
        urls: List[str],
        ips: List[str],
        domains: List[str],
        decoded_blobs: List[dict],
        techniques: List[Tuple[str, str, str]],
        telemetry: dict,
    ) -> str:
        cps = telemetry.get("cps", "Unknown")
        dev = telemetry.get("device_name", "External USB HID Device")
        conf = telemetry.get("confidence", "1.0")

        tech_rows = "\n".join(f"| `{t[0]}` | **{t[1]}** | {t[2]} |" for t in techniques)
        url_list = "\n".join(f"- `{u}`" for u in urls) if urls else "- *None identified*"
        ip_list = "\n".join(f"- `{ip}`" for ip in ips) if ips else "- *None identified*"

        decoded_section = ""
        if decoded_blobs:
            decoded_section = "### De-obfuscated Payload Elements\n\n"
            for b in decoded_blobs:
                decoded_section += f"**Encoded string**: `{b['encoded']}`\n\n```text\n{b['decoded']}\n```\n\n"

        return f"""# 🛡 DuckyGuard Incident Response Report

**Incident ID**: `DG-INC-{timestamp}`  
**Triage Date**: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Threat Status**: 🟢 **NEUTRALIZED & CONTAINED (Zero Command Execution)**  
**Hardware Attacker Device**: `{dev}`  
**Injection Velocity**: `{cps} keystrokes/sec` (Confidence: {int(float(conf)*100)}%)  

---

## 1. Executive Summary
An unauthorized Physical HID injection attack (Rubber Ducky / BadUSB) was intercepted on endpoint. The keystroke burst was detected within milliseconds by the timing dynamics engine. DuckyGuard's focus-stealing Decoy Sink pulled system focus, routing all injected input into a quarantined text buffer. **No payload components executed in the host shell or terminal.**

---

## 2. MITRE ATT&CK® TTP Matrix

| Technique ID | Technique Name | Observation Details |
| :--- | :--- | :--- |
{tech_rows}

---

## 3. Indicators of Compromise (IOCs)

### Remote Infrastructure & Dropper URLs
{url_list}

### Network IP Addresses
{ip_list}

{decoded_section}

---

## 4. Full Intercepted Payload (Forensic Stream)

```text
{clean_text.strip()}
```

---

## 5. Recommended Remediation & IR Steps
1. **Physical Security**: Locate and isolate the physical USB device from the host port.
2. **Firewall / Proxy Block**: Add extracted domains and IPs to corporate perimeter DNS/egress blocklists.
3. **Endpoint Verification**: Inspect `/tmp/` and user download folders for any artifacts referenced in dropper URLs.
4. **Deploy YARA Signature**: Distribute the attached YARA rule `rule-{timestamp}.yar` across your fleet.
"""

    def _generate_yara_rule(self, timestamp: str, clean_text: str, urls: List[str], ips: List[str]) -> str:
        rule_name = f"DuckyGuard_BadUSB_Payload_{timestamp.replace('-', '_')}"

        strings_block = []
        idx = 1

        for u in urls[:3]:
            safe_u = u.replace("\\", "\\\\").replace('"', '\\"')
            strings_block.append(f'        $url{idx} = "{safe_u}" ascii wide')
            idx += 1

        for ip in ips[:2]:
            strings_block.append(f'        $ip{idx} = "{ip}" ascii')
            idx += 1

        # Extract distinctive subcommands
        keywords = ["curl", "wget", "powershell", "chmod +x", "open -a", "base64", "osascript"]
        for kw in keywords:
            if kw in clean_text.lower():
                strings_block.append(f'        $cmd{idx} = "{kw}" ascii nocase')
                idx += 1

        if not strings_block:
            strings_block.append('        $generic = "curl" ascii nocase')

        strings_str = "\n".join(strings_block)

        return f"""rule {rule_name}
{{
    meta:
        description = "Automated rule generated by DuckyGuard for intercepted BadUSB payload"
        author = "Steven Hainley (DuckyGuard)"
        date = "{datetime.datetime.now().strftime("%Y-%m-%d")}"
        threat_type = "BadUSB / HID Injection Dropper"
        mitre_technique = "T1200, T1059"

    strings:
{strings_str}

    condition:
        any of them
}}
"""
