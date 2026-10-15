"""
Build the scene assets from a single reference photo of the P2 grid view (lights lit).

  1. Lights-off plate: inside each of the five light pods the lit LED lens is turned into a
     dark lens (luminance texture kept, red emission removed) and the red spill around the
     gantry is neutralised.
  2. Light states k = 1..5: crops of the gantry where pods 1..k are restored from the photo,
     so every lit lamp is the photo's own pixels.
  3. Ambient "life" layers (all opacity-only on the page, nothing moves):
       - heat haze: three copies of the far-straight strip, each displaced by a smooth
         sub-pixel noise field, faded in and out over the static plate
       - shimmer points: the brightest floodlight / building / city light sources, found
         automatically outside the cockpit and the gantry
       - LED points: small red lights on the cars ahead
       - flash zones: grandstand and pit-building areas where camera flashes may appear
  4. Writes src/assets/scene/photo-*.webp and src/scene/scenes.json.

Usage: python render/photo_plate.py <photo> <assets dir> <scenes.json>
"""

from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

# ---------------------------------------------------------------- photo-specific geometry
# All geometry is measured on the 1672x941 reference and scaled by K = width / 1672, so an
# upscaled copy of the same photo (e.g. 3840 px) yields identical layouts.
REF_W = 1672
K = 1.0


def k(v):
    """Reference pixels -> working pixels."""
    return v * K


def kr(rect):
    return tuple(int(round(v * K)) for v in rect)


# Light pods (x0, y0, x1, y1) in reference pixels.
PODS = [(694, 171, 739, 241), (755, 171, 800, 241), (816, 171, 861, 241), (878, 171, 922, 241), (939, 171, 984, 241)]
LAMP_CENTRES = [(716.5, 204.5), (776.5, 203.5), (837.5, 203.5), (899.0, 202.5), (961.5, 202.5)]
LENS_R = 22.0
GANTRY = (660, 150, 1020, 262)        # region whose red spill is neutralised / cropped for states
HAZE = (430, 272, 1240, 398)          # far end of the straight, below the gantry, above the car ahead
BEAM = (320, 80, 1310, 168)           # overhead gantry beam with the banner: always static
FOREGROUND_TOP = 540                  # below this the cockpit/halo fills the frame: no effects
LEDS = [(860.0, 479.0, 15.0), (524.0, 444.0, 8.0), (663.5, 437.0, 5.5), (729.5, 434.0, 4.0)]
FLASH_ZONES = [(0, 120, 330, 380), (1240, 110, 1672, 380), (520, 330, 720, 400)]  # stands, pit building


def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255


def to_img(a, mode="RGB"):
    return Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), mode)


def redness(a):
    return np.clip(a[..., 0] - np.maximum(a[..., 1], a[..., 2]), 0, 1)


def lights_off(src):
    out = src.copy()
    x0, y0, x1, y1 = kr(GANTRY)
    g = out[y0:y1, x0:x1]
    lum = g @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # unlit lens: a faint echo of the LED grid (the reflectors still catch some floodlight)
    lens = np.stack([lum * 0.075 + 0.02, lum * 0.065 + 0.019, lum * 0.065 + 0.021], -1)
    disc = np.zeros(g.shape[:2], np.float32)
    yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0].astype(np.float32)
    for (cx, cy) in LAMP_CENTRES:
        d = np.hypot(xx - (k(cx) - x0), yy - (k(cy) - y0))
        disc = np.maximum(disc, np.clip((k(LENS_R + 1.5) - d) / k(3.0), 0, 1))
    # elsewhere only the red cast goes: the navy banner / grey housing keep their own hue
    neutral = g.copy()
    neutral[..., 0] = np.minimum(g[..., 0], g[..., 1] + 0.015)
    w = disc[..., None]
    out[y0:y1, x0:x1] = w * lens + (1 - w) * neutral
    return out


def light_states(src, off):
    """Cumulative states, cropped to GANTRY. Pod k is restored with a soft-edged mask."""
    x0, y0, x1, y1 = kr(GANTRY)
    states = []
    acc_mask = np.zeros((y1 - y0, x1 - x0), np.float32)
    for pod in PODS:
        px0, py0, px1, py1 = kr(pod)
        m = np.zeros_like(acc_mask)
        # the pod plus the halo its lamp throws onto the housing around it
        m[py0 - y0 - round(k(6)):py1 - y0 + round(k(6)), px0 - x0 - round(k(7)):px1 - x0 + round(k(7))] = 1
        acc_mask = np.maximum(acc_mask, ndimage.gaussian_filter(m, k(2.5)))
        mk = acc_mask[..., None]
        states.append(src[y0:y1, x0:x1] * mk + off[y0:y1, x0:x1] * (1 - mk))
    return states


def haze_frames(off, n=3, seed=7):
    x0, y0, x1, y1 = kr(HAZE)
    strip = off[y0:y1, x0:x1]
    h, w, _ = strip.shape
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # stronger towards the road surface (heat rises off the asphalt), fading out at the top
    ramp = np.clip((yy / h - 0.25) / 0.6, 0, 1) ** 1.5
    # feathered alpha so the strip melts into the plate
    fx = np.minimum(np.clip(xx / k(60), 0, 1), np.clip((w - 1 - xx) / k(60), 0, 1))
    fy = np.minimum(np.clip(yy / k(30), 0, 1), np.clip((h - 1 - yy) / k(18), 0, 1))
    alpha = (fx * fy)[..., None]
    frames = []
    for _ in range(n):
        nx = ndimage.gaussian_filter(rng.standard_normal((h, w)), (k(2.5), k(9)))
        ny = ndimage.gaussian_filter(rng.standard_normal((h, w)), (k(2.5), k(9)))
        nx *= k(0.7) / (np.abs(nx).max() + 1e-6)
        ny *= k(0.45) / (np.abs(ny).max() + 1e-6)
        sx = np.clip(xx + nx * ramp, 0, w - 1)
        sy = np.clip(yy + ny * ramp, 0, h - 1)
        warped = np.stack([ndimage.map_coordinates(strip[..., c], [sy, sx], order=1) for c in range(3)], -1)
        frames.append(np.concatenate([warped, alpha], -1))
    return frames


def shimmer_points(src, limit=26):
    lum = src @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    bright = lum > 0.93
    bright[380:] = False  # cars and cockpit: no shimmer
    gx0, gy0, gx1, gy1 = GANTRY
    bright[gy0 - 10:gy1 + 10, gx0 - 10:gx1 + 10] = False
    lab, n = ndimage.label(bright)
    pts = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        size = int((lab[sl] == i).sum())
        if size < 6:
            continue
        cy, cx = ndimage.center_of_mass(lab == i)
        pts.append((size, float(cx), float(cy)))
    pts.sort(reverse=True)

    def clear_of(rect, cx, cy, r, pad=6):
        x0, y0, x1, y1 = rect
        dx = max(x0 - cx, 0, cx - x1)
        dy = max(y0 - cy, 0, cy - y1)
        return dx * dx + dy * dy > (r + pad) ** 2

    radius = lambda s: min(8 + np.sqrt(s) * 2.2, 34)  # noqa: E731
    # spread the picks, and keep every glow clear of the gantry, its beam and the haze strip
    chosen = []
    for size, cx, cy in pts:
        r = radius(size)
        if not all(clear_of(R, cx, cy, r) for R in (GANTRY, BEAM)):
            continue
        if all((cx - a) ** 2 + (cy - b) ** 2 > 30 ** 2 for _, a, b in chosen):
            chosen.append((size, cx, cy))
        if len(chosen) >= limit:
            break
    return [{"x": round(cx, 1), "y": round(cy, 1), "r": round(radius(s), 1)} for s, cx, cy in chosen]


def led_points(src):
    """Rear rain lights of the cars ahead (picked by eye; automatic detection also catches red
    bodywork). Radius covers the lamp and its immediate glow."""
    return [{"x": x, "y": y, "r": r} for x, y, r in LEDS]


def main():
    """photo_plate.py <reference photo> <assets dir> <scenes.json> [--hires=<same photo, upscaled>]

    Effect anchors are always detected on the reference photo. Pixel assets (plates, light
    states, haze) come from the hi-res copy when given; a reference-width plate is written too
    so smaller screens don't download the large one. Manifest coordinates stay in reference
    pixels (the page only uses them as fractions)."""
    global K
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    photo, assets, manifest_path = args[:3]
    ref = load(photo)
    rh, rw, _ = ref.shape
    assert rw == REF_W, f"reference must be {REF_W} px wide, got {rw}"
    src = load(opts["hires"]) if "hires" in opts else ref
    h, w, _ = src.shape
    K = w / REF_W
    off = lights_off(src)

    plates = []
    for pw in sorted({w, REF_W}):
        img = to_img(off)
        if pw != w:
            img = img.resize((pw, round(h * pw / w)), Image.LANCZOS)
        name = f"photo-plate-{pw}.webp"
        img.save(f"{assets}/{name}", "WEBP", quality=90, method=6)
        plates.append({"file": name, "w": pw})
    light_files = []
    for i, st in enumerate(light_states(src, off), start=1):
        name = f"photo-lights-{i}.webp"
        to_img(st).save(f"{assets}/{name}", "WEBP", quality=94, method=6)
        light_files.append(name)
    haze_files = []
    for i, fr in enumerate(haze_frames(off), start=1):
        name = f"photo-haze-{i}.webp"
        to_img(fr, "RGBA").save(f"{assets}/{name}", "WEBP", quality=90, method=6)
        haze_files.append(name)

    K = 1.0  # anchors in reference pixels
    x0, y0, x1, y1 = GANTRY
    hx0, hy0, hx1, hy1 = HAZE
    fx = {
        "haze": {"x": hx0, "y": hy0, "w": hx1 - hx0, "h": hy1 - hy0, "files": haze_files},
        "shimmer": shimmer_points(ref),
        "leds": led_points(ref),
        "flashZones": [{"x": a, "y": b, "w": c - a, "h": d - b} for a, b, c, d in FLASH_ZONES],
    }
    base = {
        "width": REF_W,
        "height": rh,
        "plates": plates,
        "lights": {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "files": light_files},
        "fx": fx,
    }
    manifest = {
        "landscape": {**base, "focus": [0.5, 0.42]},
        # phones crop the same plate around the lights, the car ahead and the wheel
        "portrait": {**base, "focus": [0.5, 0.5]},
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("plates", [p["w"] for p in plates], "shimmer", len(fx["shimmer"]))


if __name__ == "__main__":
    main()
