# LIGHTS OUT — F1 Start Reaction Test

An onboard, driver's-eye reaction test. You sit on **grid slot P2** of a Singapore-style night street
circuit. Tap, click or press **Space** to start: five red lights come on one second apart, hold for a random
0.2–3.0 s, then all go out at once. React. Your time is shown in whole milliseconds. Under 100 ms you get a
question you may want to answer honestly.

- React 19 + Vite + TypeScript (strict) + Tailwind CSS v4, no server, fully static
- No audio, no accounts, no history/leaderboard — only this attempt's time

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # engine unit tests (vitest)
npm run build      # type-check + static build into dist/
npm run preview    # serve dist/ locally
```

## Deploying

`dist/` is a plain static site built with a relative base (`./`), so it works from any host or sub-path:

- **GitHub Pages** — `.github/workflows/deploy.yml` builds and publishes on every push to `main`
  (enable *Settings → Pages → Source: GitHub Actions* once).
- **Netlify / Vercel / Cloudflare Pages** — build command `npm run build`, output directory `dist`.
- **Any web server / S3** — upload the contents of `dist/`.

## How the timing works

`src/game/engine.ts` is a framework-free state machine:
`INTRO → ARMED → COUNTDOWN (lights 1–5) → WAITING_FOR_LIGHTS_OUT → REACTION_WINDOW → RESULT`, plus `FALSE_START`.

- **One clock.** Everything is on the monotonic `performance.now()` timeline. `Date.now()` is never used.
- **Drift-free schedule.** On start, all five switch-on times are computed as absolute timestamps
  (`first + k × 1000 ms`) and the lights-out deadline as `scheduledFifthLight + hold`. No chained `setTimeout`s.
- **Frame-synchronised visuals.** A `requestAnimationFrame` loop applies each change on the first frame at or
  after its deadline, writing directly to the DOM (an opacity flip on pre-decoded images). React is not involved
  and is not even notified on the lights-out frame.
- **Measuring from what you could actually see.** The lights are switched off in frame *N*; the timestamp of
  frame *N+1* — when frame *N* has been handed to the display — is recorded as `lightsOutTime`. The clock
  therefore never starts before the dark lights could be on screen.
- **Input time = event time.** `pointerdown` and Space `keydown` use the event's own `timeStamp`
  (when the OS delivered it), not the time the handler happened to run.
- **One judgement, no double verdicts.** A press before `lightsOutTime` is a false start; after it, a reaction.
  A press that arrives between the DOM switch and the next frame is held and decided with that same single
  comparison.
- **Abuse & glitches.** Space auto-repeat is ignored and a release is required between presses, so holding a key
  (or finger) through lights-out never registers. Presses within 40 ms of each other count once. Results are locked
  for 700 ms so a double tap can't skip them. The page listens to `pointerdown` only, so one tap can't also count
  as a `click`. Hidden tab / `pagehide` / a frame stall over 250 ms / a camera switch on rotation all cancel
  the attempt and return to the intro. Input is ignored until every image is decoded.

Recorded per attempt (`engine.timeline`): `sequenceStartTime`, `lightSchedule`, `lightCommitTimes`,
`fifthLightTime`, `holdMs`, `lightsOutDeadline`, `lightsOutCommitTime`, `lightsOutTime`, `inputTime`, `reactionRaw`.
Open the site with `?debug` to expose the engine as `window.__lightsOut` for inspection.

**Limits.** A web page can't see display scan-out, panel response, touch-controller or USB-polling latency.
These add a device-dependent amount (often 10–50 ms, more on some phones / TVs) to every result. Times are a
good relative measure on one device, not a lab measurement.

## Graphics — what they are and where they come from

All imagery is **original computer-generated work made for this project**. No photographs, broadcast frames,
team assets or third-party images are included.

- `render/scene.py` builds the whole scene procedurally with Blender 5.2 (the `bpy` Python module) — our car's
  cockpit, halo, steering wheel and gloves, the P1 car ahead (offset to the left, 8 m up the staggered grid), the
  start gantry, floodlight poles, walls, debris fences, pit building, grandstand and a distant city skyline with an
  observation wheel — and renders it with Cycles (physically based path tracing, OpenImageDenoise).
- Two cameras from the same eye point: 16:9 landscape and 9:19.5 portrait, so phones get a real framing instead
  of a stretched crop.
- Two passes per camera: the *plate* (start lights dark, denoised) and a *lamps* pass containing only each light
  column's camera-visible emission, rendered just for the gantry region without denoising.
  `render/post.py` composites them (haze from the mist pass, bloom, a filmic tone curve, mild lens distortion,
  vignette and grain) and writes the plate plus five cumulative light-state crops. Every light state is therefore
  an exact render of the same scene, not a drawn overlay.
- Cars and liveries are fictional. There are no team, sponsor, tyre-brand or FIA marks. Fonts: Titillium Web
  (SIL Open Font License, via `@fontsource/titillium-web`).

**Honest assessment.** The renders are physically lit CG built from procedural geometry, not photographs. They
read as a night-time onboard view, but close up the models are simpler than a real car (the gloves, mirrors and the
P1 car in particular) and a trained eye will see CG. Sourcing licensed real onboard photography, or replacing the
procedural models with a detailed licensed car model, is the obvious next step — see the asset pipeline below.

### Re-rendering the assets

```bash
python3 -m venv .venv && .venv/bin/pip install bpy==5.2.2 OpenEXR pillow numpy
OUT=/tmp/lo
.venv/bin/python render/scene.py --aspect landscape --width 2400 --samples 96 --out $OUT/L --tex $OUT
.venv/bin/python render/scene.py --aspect landscape --width 2400 --pass lamps --out $OUT/L-lamps --tex $OUT
.venv/bin/python render/scene.py --aspect portrait --width 1170 --samples 96 --out $OUT/P --tex $OUT
.venv/bin/python render/scene.py --aspect portrait --width 1170 --pass lamps --out $OUT/P-lamps --tex $OUT
.venv/bin/python render/post.py export $OUT/L landscape src/assets/scene src/scene/scenes.json --exposure=0.55 --focus=0.5,0.42 --widths=0,1600
.venv/bin/python render/post.py export $OUT/P portrait  src/assets/scene src/scene/scenes.json --exposure=0.55 --focus=0.5,0.55 --widths=0,780
```

(≈ 1 hour on a 4-core CPU.) `src/scene/scenes.json` records each plate's size, the focus point kept on screen
when cropping to the viewport, and where the light crops sit.

## Project layout

```
src/game/engine.ts       state machine + timing (no DOM, no React) — unit tested in engine.test.ts
src/game/input.ts        pointer / Space wiring, de-duplication, visibility handling
src/scene/               asset manifest, preloader, the composited stage (cover-fit around a focus point)
src/ui/                  intro / result / false-start overlay, loading screen
render/                  Blender scene generator and post-processing that produce src/assets/scene/*
```
