# Visual overhaul — research, method choice, rights tracking

Status: **Prototype built on a user-supplied reference image (§7), on a feature branch only — not cleared for
public release (§5).** Camera vibration is removed and verified (§6).

## 1. Reference research — Singapore start/finish straight

Collected through web search. The sandbox could not open the source pages or any image hosts (§4), so these
points come from the search results and need checking against real footage before final composition.

| Topic | Finding | Source |
| --- | --- | --- |
| Location | Start/finish straight built on vacant land next to the Singapore Flyer; permanent pit building; paddock beside Republic Boulevard (pit building address 1 Republic Blvd) | [Wikipedia: Marina Bay Street Circuit](https://en.wikipedia.org/wiki/Marina_Bay_Street_Circuit), [Pirelli](https://www.pirelli.com/global/en-ww/race/singapore-f1-circuit-and-its-technology) |
| Sides of the straight | Pit Grandstand sits on the outside (right-hand side) of the straight, directly opposite the pit lane, garages and podium | [oversteer48 – Pit Grandstand](https://oversteer48.com/singapore-f1-pit-grandstand/) (search summary) |
| Flyer position | The Flyer stands between the last two corners and looks down onto the pit building and grid, i.e. **beside or behind the grid**, not ahead of a car facing Turn 1 | [singaporegp.sg 2011](https://singaporegp.sg/news/2011/zone-1-ticket-holders-to-enjoy-additional-viewing-experiences-at-the-2011), [formula1.com circuit page](https://www.formula1.com/en/information.singapore-marina-baystreetcircuit.7LXNQUCHTyR5yMQPlIk7Lv.html) |
| Marina Bay Sands | No source confirms it is visible from the grid looking towards Turn 1, so **it must not be placed in the P2 view** without footage proving the sightline | search results above |
| Track lighting | ~1,500 projectors (pre-race plans said 1,600) on **horizontal aluminium trusses about 10 m above the track**, carried by steel pylons **32 m apart**, projectors about **4 m apart**, mounted on **one side of the track only** (to avoid disorienting drivers after a spin). Average ~**3,000 lux**, sized for HDTV. The trusses also carry cables, PA speakers, CCTV and advertising | [singaporegp.sg 2008](https://singaporegp.sg/news/2008/live-demonstration-of-the-2008-formula-1a-singtel-singapore-grand-prix-lighting-system/), [f1technical](https://f1technical.net/news/8034), [Philips](https://www.philips.com.sg/a-w/singapore-50-years/singapore-50-years-articles/lighting/f1-arena.html), [grandprix.com](https://grandprix.com/news/how-to-light-up-f1.html) |
| Start procedure | Five reds at 1 s intervals; then a random 0.2–3 s hold, after which all go out together. Operated by the race director from beside the line. Repeater lights can be added part-way down the grid | [formula1-dictionary](https://www.formula1-dictionary.net/f1-race-start-sequence/), [Aston Martin F1](https://www.astonmartinf1.com/en-GB/news/feature/avatrade-explains-the-f1-rulebook-race-starts), [motorsport.com](https://us.motorsport.com/f1/news/fia-start-lights-grid-bahrain/4361362/) |
| Layout changes | 2023 layout removed old turns 16–19, so references older than 2023 may show a different straight-side environment | search results (Wikipedia race pages) |

## 2. Why the current CG reads as a 10–15-year-old racing game

Reviewed from the shipped renders (desktop 2400 px, mobile 1170 px):

1. **Geometry built from primitives.** Boxes, tubes and lofted superellipses with uniform bevels. Real carbon
   bodywork has compound curvature, panel gaps, fasteners, stickers, tape and sharp trailing edges.
2. **Steering wheel.** The buttons are 2–3× too large and too saturated, the carbon checker is about 10× too
   coarse, and there are no labels, rotary detents, paddles or bezel detail. The gloves are smooth egg shapes.
3. **Materials too clean.** No roughness variation, dust, rubber pick-up, wear on the halo or scuffs on the
   cockpit rim. Highlights are perfect and uniform, which reads as plastic.
4. **Wrong lighting layout.** The scene has pole-and-arm lamps on both sides of the track. Singapore uses
   continuous trusses on one side only, about 10 m up, with projectors 4 m apart. That gives the track its very
   even, flat light and a distinctive row of glare points; the CG doesn't reproduce either.
5. **Fictional skyline.** Procedural window patterns repeat (the "barcode" look). The last iteration also added
   landmarks (resort towers, observation wheel) whose sightline from P2 is not confirmed — the Flyer is
   actually behind the grid. **That iteration was stopped and never shipped.**
6. **Missing street-circuit clutter.** Real views are full of marshal posts, TV cameras, cabling, timing
   screens, signage, people in the pit lane and on the gantry, tyre marks, kerb paint and asphalt repairs.
   Their absence is the strongest "game" signal.
7. **Optical look.** The tone curve and bloom are generic. Real broadcast onboards show compressed highlights,
   sensor noise in the shadows, sharpening halos and slightly crushed blacks.

## 3. Method comparison

| Method | Achievable realism | Rights risk | Feasible here? |
| --- | --- | --- | --- |
| A. Real photography (grid / onboard) | Highest for the background — it *is* the place | High: F1/FOM, teams and agencies own nearly all of it; CC images of this exact viewpoint are rare | **No.** All photo hosts are blocked in this sandbox (§4) |
| B. AI photorealistic generation | High for a single still if prompted with real references. Needs checking for wrong halo/wheel geometry and invented text | Medium: depends on the tool's terms; must not imitate real team liveries or logos | **No.** No image-generation tool, and model hosts are blocked |
| C. Professional 3D cockpit asset | High for the foreground (halo, wheel, carbon) | Medium: per-asset licence, often editorial-only for F1 replicas | **No.** Asset stores (Sketchfab, CGTrader, TurboSquid) are blocked |
| D. Hybrid compositing (A/B background + B/C cockpit + rendered light states) | **Best overall:** photo background, believable cockpit, physically correct light states | Inherits the risk of its inputs | **Partly.** The compositing pipeline exists (layered background / gantry / light glow / cockpit, with photo override); it only needs input images |

**Recommendation: Method D.** Use a real or AI-generated photographic background of the start/finish straight
from about 0.9 m eye height, plus a photographic cockpit foreground (AI-generated or a licensed 3D asset
rendered with matching light). Keep our own rendered light-state layers so the five reds stay physically
switchable and timing-exact. Procedural CG stays only as the fallback.

## 4. Blocker — what this environment cannot reach

The cloud environment's network policy only allows package registries and GitHub. Hosts that are refused or
unreachable include: `commons.wikimedia.org`, `upload.wikimedia.org`, `api.openverse.org`,
`images.unsplash.com`, `images.pexels.com`, `www.flickr.com`, `live.staticflickr.com`, `dl.polyhaven.org`,
`ambientcg.com`, `huggingface.co` and `cdn.jsdelivr.net`. Web page fetches also fail (DNS), so even reference
pages and images can't be inspected visually — only search-result text. There is no image-generation tool in
this session.

Ways to unblock (any one is enough to start Phase 2):

1. **You supply images.** Commit them to `reference/` (references only — never shipped) or to
   `src/assets/scene/override/` (candidate plates) and push. AI images made with your own tool work too.
2. **Open the network.** In the environment settings, add the hosts you want under *Allowed domains*
   (e.g. `commons.wikimedia.org`, `upload.wikimedia.org`, `api.openverse.org`, `sketchfab.com`), or choose a
   broader access level. See <https://code.claude.com/docs/en/cloud-environments#network-access>.
3. **An image-generation API.** Allow its domain and add your API key as an environment secret. I would
   generate the plates with prompts grounded in §1.

## 5. Rights tracking

Every external input must be listed here before it can ship. Unconfirmed rows are excluded from public builds.

| Asset | Used for | Source URL | Author / owner | Licence | Confirmed for public use? |
| --- | --- | --- | --- | --- | --- |
| Rendered CG (current site) | all imagery | `render/scene.py` (this repo) | project | own work | yes |
| Titillium Web | UI font | npm `@fontsource/titillium-web` | Accademia di Belle Arti di Urbino | SIL OFL 1.1 | yes |
| owner-supplied reference image (1672×941, not committed) → `src/assets/scene/photo-*` | base plate, light states, haze strips | supplied by the project owner in chat, 2026-10-13 | **unknown** (provenance not stated; ICC profile only, no EXIF/C2PA; likely AI-generated) | **unknown** | **NO.** Contains third-party marks (Singapore Airlines, Red Bull, Oracle, TAG Heuer, Mobil, Pepe Jeans, Armor All, INEOS, Shell, CEVA, Ferrari/Mercedes/Red Bull liveries). Needs provenance, licence and trademark clearance, or replacement, before any public deployment |

Checklist before public use of any new asset: licence permits commercial/public web use · attribution
requirements met · no F1/FOM, FIA, team, driver or sponsor marks visible (or licensed) · no identifiable people
without consent · AI tool's terms allow publication · source and date recorded above.

## 6. Camera vibration — removed

The `.engine-idle` animation (±0.35 px steps every 70 ms) was the only source of motion. The class and its
keyframes are gone, so the scene has no transform or animation in any state. Verified in Chromium at
1440×900 and 390×844 (`still.mjs`, kept outside the repo), with 54/54 checks passing:

- No running animation and no non-identity transform on the scene or any ancestor in INTRO, ARMED, COUNTDOWN,
  WAITING_FOR_LIGHTS_OUT, REACTION_WINDOW, RESULT and FALSE_START.
- Every layer `<img>` rectangle is identical across 90 consecutive frames in each state.
- Consecutive screenshots of text-free regions are pixel-identical (0 differing values) in INTRO, RESULT,
  FALSE_START and the full frame during REACTION_WINDOW.

The engine's 16 unit tests and the 45 regression browser checks still pass.

## 7. Prototype: reference plate + ambient life

Base: the owner's reference image of the P2 grid view, kept as the composition. `render/photo_plate.py` turns
it into assets; nothing is redrawn.

- **Lights off.** Inside each of the five pods the lit LED lens becomes an unlit lens (luminance texture
  kept at ~7 %, red removed). Around the gantry only the red cast is removed (R clamped to G + 0.015).
- **Light states 1–5.** Pods 1…k are restored from the photo's own pixels with soft masks (pod + 6–7 px
  spill). The timing engine and the opacity-flip switching are unchanged.
- **Ambient life.** All of it is opacity-only on layers fixed in place; nothing moves, and nothing is drawn
  over the cockpit, halo, wheel, light pods or banner beam:

| Effect | Where | Strength | Frequency |
| --- | --- | --- | --- |
| Light shimmer | 26 brightest floodlight / building / city sources (auto-detected; kept clear of the gantry, beam and cars) | warm radial glow at 2–12 % opacity, screen blend | each light on its own 2.3–6.9 s cycle with irregular keyframes and a random phase → no visible repetition |
| Rear rain-light liveliness | 4 rain lights on the cars ahead | red glow at 0–13 % opacity | 1.1–1.9 s cycles |
| Heat haze | far end of the straight (x 430–1240, y 272–398 of 1672×941), feathered edges | 3 copies displaced by a smooth noise field, ≤ 0.7 px horizontal / 0.45 px vertical, strongest just above the road | cross-fade cycles of 3.1 / 4.5 / 5.9 s |
| Camera flashes | left grandstand, pit-building balconies, far stand | ~14 px burst (0.9 % of plate width), 160 ms, 25 % with a weaker pre-flash | one every 4–11 s |

**Start-sequence freeze.** All four effects run on the INTRO, RESULT and FALSE_START screens only. From the
start press (ARMED) until the reaction is recorded, every effect pauses exactly where it is
(`animation-play-state: paused`) and a flash in flight is cancelled. Verified: 0 of 33 effect animations
running and 0 opacity changes over 60 frames in ARMED, COUNTDOWN and WAITING_FOR_LIGHTS_OUT; the whole
REACTION_WINDOW frame is pixel-identical; effects resume on RESULT and FALSE_START.

Measured in Chromium (1440×900 and 390×844), 67/67 checks: the cockpit, halo, wheel, light pods and banner
beam are pixel-identical across 2 s in every state; only opacity animates, only inside the ambience layer;
no element changes position or size; no flash fired during a start. Background change: mean
≈ 0.2/255 per channel, 99th percentile of changed pixels 16/255, max 41/255 (haze over high-contrast city
edges); 8 % of the frame changes at all. `prefers-reduced-motion` turns all of it off.

**4K upscaling — evaluated, not applied.** `render/upscale.py` runs Real-ESRGAN (RRDBNet, BSD-3 weights
`RealESRGAN_x2plus` / `RealESRGAN_x4plus` from github.com/xinntao/Real-ESRGAN releases) on CPU; results were
resampled to 3840 px and compared at 100 % against Lanczos on the banner text, grandstand crowd, steering-wheel
display, the car ahead and the far city. ESRGAN sharpens hard edges (banner lettering) but **invents
detail**: the crowd turns into painterly smears with hard white blobs, the wheel display grows fake glyphs,
and the city loses its night-haze softness. Lanczos only enlarges (no new information — the same as the
browser scaling the 1672 px plate). Neither meets the bar, so the plate stays at its native 1672×941.
`photo_plate.py --hires=<file>` accepts a higher-resolution copy of the same photo if a genuine one (e.g. the
original at full resolution) becomes available.

Known limits of the prototype:
- 1672×941 source: soft on 1440p/4K and on phones (the portrait view is a 434 px wide crop upscaled ≈ 2.7×).
- The ambience is a light layer on a still. It can't add real crowd or vehicle motion.
- Rights: see §5 — this plate must not ship publicly as is.
