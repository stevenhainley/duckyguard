# DuckyGuard Threat Model & Attack Surface Analysis

This document details the threat landscape, attacker capabilities, and defensive boundaries of DuckyGuard.

---

## 1. Threat Scenarios

### Scenario A: The Physical Drop Attack (Lost USB Drive / BadUSB)
- **Vector**: An attacker leaves a USB flash drive or Rubber Ducky in an office lobby, conference room, or campus library.
- **Payload Goal**: An unsuspecting victim plugs it in; the device enumerates as a keyboard, launches Terminal/PowerShell, downloads a secondary backdoor (C2 implant), and unmounts in under 3 seconds.
- **DuckyGuard Defense**: Intercepted at character 10. Decoy sink captures the URL and command; zero execution on host; incident report flags the C2 server immediately.

### Scenario B: The Walk-by Attacker (Flipper Zero / Evil Maid)
- **Vector**: A visitor, rogue contractor, or insider plugs a Flipper Zero or Raspberry Pi Pico into an unlocked laptop when the user steps away for coffee.
- **Payload Goal**: Quick credential harvest or SSH key exfiltration via BadUSB script.
- **DuckyGuard Defense**: The USB watcher catches the new HID enumeration; keystroke dynamics trigger the topmost quarantine alert with an audible bell; the decoy captures the exfiltration script and denies shell access.

### Scenario C: Trojanized Hardware (O.MG Cable / USB Dongle)
- **Vector**: A covert USB charging cable equipped with an embedded Wi-Fi microcontroller triggers keystroke injection remotely via an attacker's phone.
- **DuckyGuard Defense**: Detected via keystroke velocity and zero-variance timing entropy, regardless of the physical form factor of the cable.

---

## 2. Attacker Tactics vs. DuckyGuard Mitigations

| Attacker Tactic | Attacker Mechanism | DuckyGuard Defense |
| :--- | :--- | :--- |
| **High-Speed Burst** | 50–100 chars/sec without delay | Blocked by Velocity Engine ($>20\text{ cps}$) |
| **Uniform Timing Delays** | `delay(20)` to evade rate limiters | Blocked by Jitter Engine ($\sigma < 12\text{ms}$) |
| **New Hardware Insertion** | Plugging in right before typing | Blocked by USB Temporal Correlation ($\le 5\text{s}$) |
| **Encoded Base64 Strings** | Evading basic string pattern matchers | Caught by Base64 regex & automatic triage decoder |
| **Focus Hijacking via Cmd+Tab** | Attacker tries to refocus Terminal | Decoy Sink enforces continuous focus lock on loss |

---

## 3. Assumptions & Limitations

- **Accessibility Permissions**: Under macOS, DuckyGuard requires Accessibility permissions in `System Settings -> Privacy & Security -> Accessibility` to observe global input events via `pynput` / CoreGraphics event taps.
- **Slow Injection (< 8 chars/sec)**: If an attacker deliberately slows down their BadUSB payload to mimic human typing speed (e.g., 6 chars/sec), the attack takes 30–60 seconds to finish typing a payload. In an in-person attack, this vastly increases the attacker's physical exposure and gives the user time to notice and unplug the device.
