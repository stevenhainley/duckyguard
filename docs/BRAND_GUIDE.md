# 🛡 DuckyGuard Brand & Design System Guide
**A product by sh. industries · Engineered by Steven Hainley**  
*Version 1.0 — October 2026*

---

## 1. Brand Essence & Story

### The Problem We Solve
Every operating system in the world suffers from an inherent architectural vulnerability: **operating systems implicitly trust keyboards**. When a malicious USB microcontroller (Rubber Ducky, Flipper Zero, Teensy, Raspberry Pi Pico) is inserted, it emulates a human keyboard and injects devastating shell commands at 100 characters per second. Traditional antivirus and EDR only alert *after* the malware has already dropped.

### The Mission
**DuckyGuard stops physical keystroke injection before the first command executes.** It neutralizes the attack at the input and window management layer, sinking the payload into an isolated sandbox and generating real-time forensic threat intelligence.

### Brand Voice & Positioning
* **Category**: Autonomous Endpoint Defense / Physical Hardware Security.
* **Personality**: Tactical, highly technical, approachable, and unmistakably distinct. It combines the rigorous engineering of enterprise endpoint security with the playful retro craft of indie software.
* **Taglines**:
  - *Primary*: **"Autonomous Endpoint Defense Against Physical HID Injection."**
  - *Community / Hacker*: **"Because keyboards shouldn't have root."**
  - *Product Kicker*: `SH. INDUSTRIES // PHYSICAL ENDPOINT DEFENSE`

---

## 2. The Official Mascot: "Aegis Ducky"

The official DuckyGuard mascot is **Aegis Ducky** — a charming retro pixel-art yellow duck standing alert, equipped with a steel-rimmed heater shield featuring an electric cyber-orange core.

```
       [🦆] The Anatomy of Aegis Ducky
       
           ▲    (Curious, alert black pixel eye)
          /█\   
        [ 🐤 ]  (Chunky retro yellow pixel body)
         /   \  
       [   🛡 ] (Heater defense shield: steel rim + orange core)
        |     |
       [  🦶  ] (Two grounded black pixel feet)
```

### Trademark & Differentiation Analysis
* **Hak5 Rubber Ducky**: Uses a generic photographic/vector yellow bath duck with sunglasses or pirate skulls. It symbolizes *offensive injection*.
* **DuckDuckGo**: A white cartoon goose/duck with a green bow tie.
* **Cyberduck**: An FTP client with an open-beak bath toy duck.
* **DuckyGuard Uniqueness**: Our duck is **a defender, not a toy**. The pixel-art medieval heater shield is the core visual anchor. It communicates that the duck is actively guarding the port and deflecting rogue keystroke packets.

### Mascot Usage Rules:
1. **Always Crisp**: Must be rendered with `image-rendering: pixelated;` or integer scaling (`Image.NEAREST`). Never blur or apply anti-aliasing to the pixel sprite.
2. **Never Remove the Shield**: The shield is what transforms the mascot from a generic duck into the symbol of DuckyGuard.
3. **Canvas Background**: Always set on warm creme-orange (`#FAF5EE` / `#FFF1E6`) or dark obsidian ink (`#0E0E0D`).

---

## 3. Color Palette: The Modern Creme-Orange System

DuckyGuard adopts the **Awwwards-winning light creme aesthetic** — warm luxury paper surfaces combined with high-contrast typography and glowing cyber orange accents.

### Core Swatches

| Swatch | Hex Code | Token Name | Application |
| :--- | :--- | :--- | :--- |
| ![#FAF5EE](https://via.placeholder.com/15/FAF5EE/000000?text=+) | `#FAF5EE` | `bg-creme` | Primary window background (warm tactile paper) |
| ![#FFFFFF](https://via.placeholder.com/15/FFFFFF/000000?text=+) | `#FFFFFF` | `panel-white` | Raised card surfaces, dialog boxes, panels |
| ![#EFE5D8](https://via.placeholder.com/15/EFE5D8/000000?text=+) | `#EFE5D8` | `border-warm` | 1px hairline dividers and card outlines |
| ![#FF6B00](https://via.placeholder.com/15/FF6B00/000000?text=+) | `#FF6B00` | `accent-orange`| Signature Cyber Orange (visor, shield, primary CTAs) |
| ![#FFA31A](https://via.placeholder.com/15/FFA31A/000000?text=+) | `#FFA31A` | `accent-amber` | Glowing telemetry highlights, active threat alerts |
| ![#FFF0E5](https://via.placeholder.com/15/FFF0E5/000000?text=+) | `#FFF0E5` | `orange-tint`  | Soft peach badge background, active tab pill |
| ![#059669](https://via.placeholder.com/15/059669/000000?text=+) | `#059669` | `mint-green`   | System armed, healthy telemetry, secure state |
| ![#ECFDF5](https://via.placeholder.com/15/ECFDF5/000000?text=+) | `#ECFDF5` | `mint-tint`    | Background for safe status pills |
| ![#DC2626](https://via.placeholder.com/15/DC2626/000000?text=+) | `#DC2626` | `danger-red`   | Disarmed warning, active attack interception |
| ![#1C1917](https://via.placeholder.com/15/1C1917/000000?text=+) | `#1C1917` | `text-ink`     | Deep stone ink for razor-sharp typography |
| ![#78716C](https://via.placeholder.com/15/78716C/000000?text=+) | `#78716C` | `text-muted`   | Secondary labels, descriptions, timestamps |

---

## 4. Typography Hierarchy

| Role | Font Family | Weight | Size | Letter Spacing | Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Eyebrow Kicker** | `ui-monospace`, Menlo | Bold (700) | 9–10px | `0.14em` | UPPERCASE |
| **App Title** | `SF Pro Display`, system | ExtraBold (800) | 19–22px | `-0.02em` | Title Case |
| **Metric Hero** | `SF Pro Display`, system | Bold (800) | 32–36px | `-0.03em` | Standard |
| **Card Headings**| `SF Pro Text`, system | Bold (700) | 14–15px | `-0.01em` | Standard |
| **Body Text** | `SF Pro Text`, system | Medium (500) | 12–13px | `normal` | Standard |
| **Code / Telemetry**| `ui-monospace`, SF Mono | Regular (500) | 11–12px | `normal` | Monospace |

---

## 5. UI Component Architecture (The Linear / Awwwards Standard)

1. **Card Elevation**:
   ```css
   background: #FFFFFF;
   border: 1px solid #EFE5D8;
   border-radius: 16px;
   box-shadow: 0 4px 20px -2px rgba(28, 25, 23, 0.04), 0 0 0 1px #EFE5D8;
   ```
2. **Status Pills**:
   - Rounded 999px pills with a pulsing dot indicator:
     ```css
     background: #ECFDF5;
     color: #059669;
     border: 1px solid #A7F3D0;
     border-radius: 999px;
     ```
3. **Integrated Traffic Lights**:
   - macOS native titlebar is transparent (`titlebarAppearsTransparent = true`), allowing traffic lights to sit harmoniously alongside the brand header with `-webkit-app-region: drag`.
4. **Interactive Mascot Badge**:
   - 46×46 squircle container with a soft orange outline `#FED7AA` and a subtle hover bounce:
     ```css
     transform: scale(1.08) rotate(-3deg);
     ```

---

## 6. Applications & Merch Concept

* **macOS App Icon**: High-res retina `AppIcon.icns` on the light creme background.
* **GitHub Repository Banner**: 16:9 banner featuring Aegis Ducky standing on a circuit board line with the tagline.
* **Die-Cut Laptop Stickers**: Aegis Ducky cut out with a 2mm white vinyl border — a staple for DEF CON, security conferences, and hackathons.
