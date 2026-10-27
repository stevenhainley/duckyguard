"""
DuckyGuard - incidents: what was blocked, why, and the exportable report.

An incident is one blocked burst. It records the verdict that triggered the
block, the keys that were dropped while quarantine was active, the keyboard
the burst is attributed to, and a plain-English explanation. Exporting
produces a Markdown report; indicators (URLs, IPs), a MITRE ATT&CK mapping and
a YARA rule are included only when the analyzer actually found something to
base them on.
"""

from __future__ import annotations

import datetime
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from .analyzer import ForensicThreatAnalyzer

_YARA_SAFE = re.compile(r'[^\x20-\x7e]')


def new_incident_id(ts: Optional[float] = None) -> str:
    ts = ts or time.time()
    return datetime.datetime.fromtimestamp(ts).strftime("%Y%m%d-%H%M%S-") + f"{int((ts % 1) * 1000):03d}"


def build_incident(verdict: dict, keyboard: Optional[dict], prefix_text: str,
                   simulated: bool = False, started_at: Optional[float] = None) -> dict:
    started_at = started_at or time.time()
    inc = {
        "id": new_incident_id(started_at),
        "started_at": started_at,
        "ended_at": None,
        "simulated": simulated,
        "verdict": verdict,
        "keyboard": keyboard,                 # attributed, not proven (see devices.py)
        "keys_before_block": int(verdict.get("features", {}).get("burst_len", 0)),
        "prefix_text": prefix_text,           # the keys that reached the front app before the block
        "blocked_text": "",                   # keys dropped while quarantine was active
        "blocked_count": 0,
        "explanation": verdict.get("explanation", ""),
        "analysis": None,
    }
    return inc


def finalize_incident(inc: dict, blocked_text: str, blocked_count: int, ended_at: Optional[float] = None) -> dict:
    inc["blocked_text"] = blocked_text
    inc["blocked_count"] = blocked_count
    inc["ended_at"] = ended_at or time.time()
    inc["analysis"] = analyze_text(inc.get("prefix_text", "") + blocked_text)
    inc["summary"] = summarize(inc)
    return inc


def analyze_text(text: str) -> dict:
    """IOC extraction + MITRE mapping, computed in memory (no files)."""
    a = ForensicThreatAnalyzer.__new__(ForensicThreatAnalyzer)
    clean = text.replace("[BKSP]", "")
    urls = sorted(set(a.URL_PATTERN.findall(clean)))
    ips = sorted(set(ip for ip in a.IP_PATTERN.findall(clean) if not ip.startswith("127.")))
    decoded: List[dict] = []
    for cand in a.BASE64_PATTERN.findall(clean):
        try:
            import base64
            s = base64.b64decode(cand).decode("utf-8", errors="ignore")
            if any(k in s.lower() for k in ("http", "curl", "exec", "sh", "invoke", "powershell")):
                decoded.append({"encoded": cand[:30] + "...", "decoded": s})
                urls.extend(a.URL_PATTERN.findall(s))
        except Exception:
            pass
    urls = sorted(set(urls))

    techniques: List[Tuple[str, str, str]] = []
    if re.search(r"\b(curl|wget|certutil|Invoke-WebRequest)\b", clean, re.IGNORECASE):
        techniques.append(a.MITRE_MAP["ingress"])
    if re.search(r"\b(bash|zsh|sh|chmod|chown)\b", clean, re.IGNORECASE):
        techniques.append(a.MITRE_MAP["shell"])
    if re.search(r"\b(powershell|cmd\.exe|Invoke-Expression)\b", clean, re.IGNORECASE):
        techniques.append(a.MITRE_MAP["powershell"])
    if "osascript" in clean.lower():
        techniques.append(a.MITRE_MAP["applescript"])
    if decoded or re.search(r"\s-enc\b", clean, re.IGNORECASE):
        techniques.append(a.MITRE_MAP["obfuscation"])
    if urls or ips:
        techniques.append(a.MITRE_MAP["c2"])
    if "launchagents" in clean.lower() or "crontab" in clean.lower():
        techniques.append(a.MITRE_MAP["persistence"])
    # T1200 (Hardware Additions) is the technique class DuckyGuard watches for; it
    # is listed for every incident because the detection itself is the evidence.
    techniques.insert(0, a.MITRE_MAP["hardware"])

    yara = generate_yara(urls, ips, clean) if (urls or ips) else None
    return {
        "urls": urls,
        "ips": ips,
        "decoded": decoded,
        "mitre": [{"id": t[0], "name": t[1], "note": t[2]} for t in techniques],
        "yara": yara,
        "text_length": len(clean),
    }


def generate_yara(urls: List[str], ips: List[str], text: str) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    strings = []
    i = 1
    for u in urls[:4]:
        safe = _YARA_SAFE.sub("", u).replace("\\", "\\\\").replace('"', '\\"')
        strings.append(f'        $url{i} = "{safe}" ascii wide')
        i += 1
    for ip in ips[:4]:
        strings.append(f'        $ip{i} = "{ip}" ascii')
        i += 1
    body = "\n".join(strings)
    return (
        f"rule DuckyGuard_HID_payload_{stamp}\n"
        "{\n"
        "    meta:\n"
        '        description = "Indicators from a keystroke-injection payload blocked by DuckyGuard"\n'
        '        source = "DuckyGuard incident export"\n'
        f'        date = "{datetime.datetime.now().strftime("%Y-%m-%d")}"\n'
        '        note = "Strings are the URLs/IPs typed by the device. Review before deploying."\n'
        "    strings:\n"
        f"{body}\n"
        "    condition:\n"
        "        any of them\n"
        "}\n"
    )


def summarize(inc: dict) -> str:
    f = inc.get("verdict", {}).get("features", {})
    n = inc.get("keys_before_block", 0) + inc.get("blocked_count", 0)
    cps = f.get("cps", 0)
    kb = inc.get("keyboard") or {}
    who = kb.get("product") or "a keyboard"
    sim = " (simulated)" if inc.get("simulated") else ""
    return f"{who[0].upper() + who[1:]} typed {n} keys at {cps:.0f} keys/s; {inc.get('blocked_count', 0)} were blocked{sim}."


def human_time(ts: Optional[float]) -> str:
    if not ts:
        return "-"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def render_markdown(inc: dict, app_version: str) -> str:
    v = inc.get("verdict", {})
    f = v.get("features", {})
    kb = inc.get("keyboard") or {}
    an = inc.get("analysis") or {}
    lines: List[str] = []
    lines.append(f"# DuckyGuard incident {inc['id']}")
    lines.append("")
    if inc.get("simulated"):
        lines.append("> This incident was produced by DuckyGuard's own safe test. No hardware was involved.")
        lines.append("")
    lines.append(f"- Time: {human_time(inc.get('started_at'))} to {human_time(inc.get('ended_at'))}")
    lines.append(f"- DuckyGuard version: {app_version}")
    lines.append(f"- Keys that reached the front app before the block: {inc.get('keys_before_block', 0)}")
    lines.append(f"- Keys blocked during quarantine: {inc.get('blocked_count', 0)}")
    lines.append("")
    lines.append("## What happened")
    lines.append("")
    lines.append(inc.get("explanation") or v.get("explanation") or "")
    lines.append("")
    lines.append("## Why DuckyGuard decided it was not a person")
    lines.append("")
    for r in v.get("reasons", []):
        lines.append(f"- {r}")
    lines.append("")
    lines.append("| measurement | value |")
    lines.append("|---|---|")
    for k, label in (("cps", "keys per second"), ("median_iki_ms", "median gap between keys (ms)"),
                     ("cv", "gap variation (coefficient of variation)"), ("median_hold_ms", "median key hold (ms)"),
                     ("burst_len", "keys in burst at decision"), ("pattern", "payload pattern"),
                     ("new_keyboard_age_s", "untrusted keyboard attached (s ago)"), ("rule", "decision rule")):
        if k in f and f[k] is not None:
            lines.append(f"| {label} | {f[k]} |")
    lines.append("")
    lines.append("## Attributed keyboard")
    lines.append("")
    if kb:
        lines.append(f"- {kb.get('product', '?')} ({kb.get('manufacturer', '') or 'unknown maker'}), "
                     f"vendor {kb.get('vendor_hex', '????')} product {kb.get('product_hex', '????')}, "
                     f"transport {kb.get('transport', '?')}, serial {kb.get('serial') or 'none'}")
        if kb.get("vendor_note"):
            lines.append(f"- Vendor id note: {kb['vendor_note']}")
        lines.append("- Attribution is by time: this keyboard appeared shortly before the burst. "
                     "macOS does not tag key events with their source device, so this is not proof.")
    else:
        lines.append("- No untrusted keyboard appeared before the burst; the source device is unknown.")
    lines.append("")
    lines.append("## Captured text")
    lines.append("")
    lines.append("Keys that reached the front app (typed before the decision):")
    lines.append("")
    lines.append("```text")
    lines.append(inc.get("prefix_text", ""))
    lines.append("```")
    lines.append("")
    lines.append("Keys dropped by DuckyGuard:")
    lines.append("")
    lines.append("```text")
    lines.append(inc.get("blocked_text", ""))
    lines.append("```")
    lines.append("")
    if an:
        if an.get("urls") or an.get("ips"):
            lines.append("## Indicators found in the text")
            lines.append("")
            for u in an.get("urls", []):
                lines.append(f"- URL: `{u}`")
            for ip in an.get("ips", []):
                lines.append(f"- IP: `{ip}`")
            lines.append("")
        if an.get("decoded"):
            lines.append("## Decoded base64")
            lines.append("")
            for d in an["decoded"]:
                lines.append(f"`{d['encoded']}`")
                lines.append("")
                lines.append("```text")
                lines.append(d["decoded"])
                lines.append("```")
                lines.append("")
        if an.get("mitre"):
            lines.append("## MITRE ATT&CK mapping")
            lines.append("")
            lines.append("| technique | name | why it is listed |")
            lines.append("|---|---|---|")
            for t in an["mitre"]:
                lines.append(f"| {t['id']} | {t['name']} | {t['note']} |")
            lines.append("")
        if an.get("yara"):
            lines.append("## YARA rule (from the indicators above)")
            lines.append("")
            lines.append("```yara")
            lines.append(an["yara"].rstrip())
            lines.append("```")
            lines.append("")
        else:
            lines.append("No YARA rule: the text contained no URL or IP to build one from.")
            lines.append("")
    lines.append("## What to do")
    lines.append("")
    lines.append("1. Unplug any USB device you do not recognise. Check cables and hubs too.")
    lines.append("2. Look at the captured text above. If part of it ran before the block, treat that part as executed.")
    lines.append("3. If the text contains a URL or IP, block it on your network and check Downloads and /tmp.")
    lines.append("4. If this was your own keyboard, mark it trusted in DuckyGuard > Devices.")
    lines.append("")
    lines.append("Generated by DuckyGuard. Everything in this file came from this Mac; nothing was sent anywhere.")
    return "\n".join(lines) + "\n"


def export_incident(inc: dict, exports_dir: str, app_version: str) -> str:
    from .store import write_private
    os.makedirs(exports_dir, exist_ok=True)
    path = os.path.join(exports_dir, f"duckyguard-incident-{inc['id']}.md")
    write_private(path, render_markdown(inc, app_version))
    return path
