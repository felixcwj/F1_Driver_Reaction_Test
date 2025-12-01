# F1 Driver Reaction Test 🏎️🇸🇬

**"It's lights out and away we go!"**

An ultra-immersive, single-file web application designed to test your reaction times against strict Formula 1 start regulations. Featuring a "Cockpit View" and a neon-lit "Singapore GP" night mode.

## 🏁 Features

- **Strict FIA Logic:**
  - 5 Red Lights turn on at exactly 1.0s intervals.
  - **Randomized Start:** Lights go out between 0.2s and 3.0s after the 5th light (FIA Regulation).
  - **Jump Start Detection:** Moving before the lights go out results in immediate disqualification.
- **Immersive Visuals:**
  - **Cockpit Visor:** A simulated helmet view overlay.
  - **Singapore Night Mode:** Default theme featuring track floodlights and neon accents.
  - **Monza Day Mode:** Toggleable bright daylight theme.
  - **Pure CSS/SVG:** No external image assets used.
- **Precision Timing:** Reaction times measured in milliseconds using `performance.now()`.

## 🎮 How to Play

1.  **Open `index.html`** in any modern web browser.
2.  **Click "LAUNCH CLUTCH"** (or press Spacebar) to initiate the start sequence.
3.  **Focus:** Watch the 5 red lights turn on.
4.  **React:** Click or press Spacebar **IMMEDIATELY** when the lights go out.
    - _Too early?_ **JUMP START** (Disqualified).
    - _Just right?_ See your time in milliseconds.

## 🛠️ Technical Details

- **Single File:** All HTML, CSS, and JavaScript are contained within `index.html` for portability and performance.
- **Responsive:** optimized for both Desktop and Mobile (touch support included).

## 📝 Copyright

© 2025 All Rights Reserved. This project is for personal use only.
