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
# Light pods (x0, y0, x1, y1) in source pixels, measured on the 1672x941 reference.
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
    x0, y0, x1, y1 = GANTRY
    g = out[y0:y1, x0:x1]
    lum = g @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    # unlit lens: a faint echo of the LED grid (the reflectors still catch some floodlight)
    lens = np.stack([lum * 0.075 + 0.02, lum * 0.065 + 0.019, lum * 0.065 + 0.021], -1)
    disc = np.zeros(g.shape[:2], np.float32)
    yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0].astype(np.float32)
    for (cx, cy) in LAMP_CENTRES:
        d = np.hypot(xx - (cx - x0), yy - (cy - y0))
        disc = np.maximum(disc, np.clip((LENS_R + 1.5 - d) / 3.0, 0, 1))
    # elsewhere only the red cast goes: the navy banner / grey housing keep their own hue
    neutral = g.copy()
    neutral[..., 0] = np.minimum(g[..., 0], g[..., 1] + 0.015)
    w = disc[..., None]
    out[y0:y1, x0:x1] = w * lens + (1 - w) * neutral
    return out


def light_states(src, off):
    """Cumulative states, cropped to GANTRY. Pod k is restored with a soft-edged mask."""
    x0, y0, x1, y1 = GANTRY
    states = []
    acc_mask = np.zeros((y1 - y0, x1 - x0), np.float32)
    for (px0, py0, px1, py1) in PODS:
        m = np.zeros_like(acc_mask)
        # the pod plus the halo its lamp throws onto the housing around it
        m[py0 - y0 - 6:py1 - y0 + 6, px0 - x0 - 7:px1 - x0 + 7] = 1
        acc_mask = np.maximum(acc_mask, ndimage.gaussian_filter(m, 2.5))
        mk = acc_mask[..., None]
        states.append(src[y0:y1, x0:x1] * mk + off[y0:y1, x0:x1] * (1 - mk))
    return states


def haze_frames(off, n=3, seed=7):
    x0, y0, x1, y1 = HAZE
    strip = off[y0:y1, x0:x1]
    h, w, _ = strip.shape
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # stronger towards the road surface (heat rises off the asphalt), fading out at the top
    ramp = np.clip((yy / h - 0.25) / 0.6, 0, 1) ** 1.5
    # feathered alpha so the strip melts into the plate
    fx = np.minimum(np.clip(xx / 60, 0, 1), np.clip((w - 1 - xx) / 60, 0, 1))
    fy = np.minimum(np.clip(yy / 30, 0, 1), np.clip((h - 1 - yy) / 18, 0, 1))
    alpha = (fx * fy)[..., None]
    frames = []
    for _ in range(n):
        nx = ndimage.gaussian_filter(rng.standard_normal((h, w)), (2.5, 9))
        ny = ndimage.gaussian_filter(rng.standard_normal((h, w)), (2.5, 9))
        nx *= 0.7 / (np.abs(nx).max() + 1e-6)
        ny *= 0.45 / (np.abs(ny).max() + 1e-6)
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
    photo, assets, manifest_path = sys.argv[1:4]
    src = load(photo)
    h, w, _ = src.shape
    off = lights_off(src)
    to_img(off).save(f"{assets}/photo-plate-{w}.webp", "WEBP", quality=92, method=6)
    x0, y0, x1, y1 = GANTRY
    light_files = []
    for k, st in enumerate(light_states(src, off), start=1):
        name = f"photo-lights-{k}.webp"
        to_img(st).save(f"{assets}/{name}", "WEBP", quality=95, method=6)
        light_files.append(name)
    haze_files = []
    for k, fr in enumerate(haze_frames(off), start=1):
        name = f"photo-haze-{k}.webp"
        to_img(fr, "RGBA").save(f"{assets}/{name}", "WEBP", quality=92, method=6)
        haze_files.append(name)
    hx0, hy0, hx1, hy1 = HAZE
    fx = {
        "haze": {"x": hx0, "y": hy0, "w": hx1 - hx0, "h": hy1 - hy0, "files": haze_files},
        "shimmer": shimmer_points(src),
        "leds": led_points(src),
        "flashZones": [{"x": a, "y": b, "w": c - a, "h": d - b} for a, b, c, d in FLASH_ZONES],
    }
    base = {
        "width": w,
        "height": h,
        "plates": [{"file": f"photo-plate-{w}.webp", "w": w}],
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
    print("shimmer", len(fx["shimmer"]), "leds", fx["leds"])


if __name__ == "__main__":
    main()
