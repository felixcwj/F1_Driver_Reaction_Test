"""
Turn the four layer renders of one camera (see scene.py) into web assets.

Layers, back to front, as the page composites them:
  background   opaque     circuit, city, car ahead (haze + bloom)       <- replaceable by a photo
  gantry       RGBA       start-light gantry with every light dark
  lights-k     RGB/screen emission + bloom of the first k light columns (k = 1..5), cropped
  foreground   RGBA       our cockpit: bodywork, halo, mirrors, steering wheel, gloves

Each layer gets the same lens distortion, tone curve and vignette, so they register exactly.

Usage:
  python render/post.py preview <prefix> <out.png> --exposure=0.55
  python render/post.py export <prefix> <variant> <assets dir> <manifest.json> \\
      --exposure=0.55 --focus=0.5,0.42 --widths=0,1600
where <prefix> is the --out given to scene.py: <prefix>Image.exr, <prefix>Mist.exr,
<prefix>-gantryImage.exr, <prefix>-fgImage.exr, <prefix>-lampsCombined_colK.exr, <prefix>-camera.json.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import OpenEXR
from PIL import Image


def read_exr(path, alpha=False):
    with OpenEXR.File(path, separate_channels=True) as f:
        ch = f.channels()
        names = ("R", "G", "B", "A") if alpha else ("R", "G", "B")
        return np.nan_to_num(np.stack([np.asarray(ch[c].pixels, dtype=np.float32) for c in names], axis=-1))


def load(prefix):
    return {
        "bg": read_exr(prefix + "Image.exr"),
        "mist": read_exr(prefix + "Mist.exr")[..., 0],
        "gantry": read_exr(prefix + "-gantryImage.exr", alpha=True),
        "fg": read_exr(prefix + "-fgImage.exr", alpha=True),
        "cols": [read_exr(prefix + f"-lampsCombined_col{k}.exr") for k in range(1, 6)],
    }


def blur(img, radius):
    """Separable box-blur approximation of a gaussian (3 passes)."""
    if radius < 1:
        return img
    out = img
    r = int(radius)
    for _ in range(3):
        for axis in (0, 1):
            c = np.cumsum(np.pad(out, [(r + 1, r) if a == axis else (0, 0) for a in range(out.ndim)], mode="edge"), axis=axis)
            hi = np.take(c, np.arange(2 * r + 1, c.shape[axis]), axis=axis)
            lo = np.take(c, np.arange(0, c.shape[axis] - 2 * r - 1), axis=axis)
            out = (hi - lo) / (2 * r + 1)
    return out


def glow(lin, h, threshold=1.0, strength=0.4):
    """Halation around bright sources — wide and soft, as in humid night air."""
    bright = np.clip(lin - threshold, 0, 60)
    s = h / 1000.0
    return (0.55 * blur(bright, 3 * s) + 0.3 * blur(bright, 12 * s) + 0.22 * blur(bright, 45 * s)) * strength


def tonemap(lin, exposure):
    x = np.maximum(lin, 0) * exposure
    # ACES-like filmic curve (Narkowicz), applied per channel, then sRGB OETF
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
    return np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)


def lens(img, k1=0.035, ca=0.0006):
    """Mild barrel distortion + lateral chromatic aberration of a wide onboard lens (bilinear remap).
    Works on any channel count; channel 0/2 get the CA offset, others none."""
    h, w, n = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2) / (w / 2)
    ny = (yy - h / 2) / (w / 2)
    r2 = nx * nx + ny * ny
    out = np.empty_like(img)
    for c in range(n):
        extra = ca if c == 0 else (-ca if c == 2 else 0.0)
        f = 1 - k1 * r2 * 0.25 + extra * r2
        sx = np.clip(nx * f * (w / 2) + w / 2, 0, w - 1.001)
        sy = np.clip(ny * f * (w / 2) + h / 2, 0, h - 1.001)
        x0 = sx.astype(np.int32)
        y0 = sy.astype(np.int32)
        fx = sx - x0
        fy = sy - y0
        ch = img[..., c]
        out[..., c] = (ch[y0, x0] * (1 - fx) * (1 - fy) + ch[y0, x0 + 1] * fx * (1 - fy)
                       + ch[y0 + 1, x0] * (1 - fx) * fy + ch[y0 + 1, x0 + 1] * fx * fy)
    return out


def vignette(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    return (1 - 0.28 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None]


def grain(h, w, seed, amount=0.008):
    return np.random.default_rng(seed).normal(0, amount, size=(h, w, 1)).astype(np.float32)


def unpremultiply(rgba):
    a = rgba[..., 3:4]
    rgb = np.where(a > 1e-4, rgba[..., :3] / np.maximum(a, 1e-4), 0)
    return rgb, a[..., 0]


def build_layers(L, exposure):
    """Display-referred layers: background RGB, gantry RGBA, foreground RGBA, 5 glow RGB."""
    bg = lens(L["bg"])
    h, w, _ = bg.shape
    mist = lens(L["mist"][..., None])[..., 0]
    vig = vignette(h, w)

    # humid haze: distance fades towards a warm, light-polluted grey-brown
    haze_col = np.array([0.03, 0.021, 0.016], np.float32)
    k = (np.clip(mist, 0, 1) ** 0.8)[..., None] * 0.55
    bg = bg * (1 - k) + haze_col * k
    bg = bg + glow(bg, h)
    bg_out = np.clip(tonemap(bg, exposure) * vig + grain(h, w, 1), 0, 1)

    def rgba_layer(rgba, seed):
        prem = lens(rgba)
        rgb, a = unpremultiply(prem)
        out = np.clip(tonemap(rgb, exposure) * vig + grain(h, w, seed) * (a[..., None] > 0), 0, 1)
        return np.concatenate([out, a[..., None]], axis=-1)

    gantry = rgba_layer(L["gantry"], 2)
    fg = rgba_layer(L["fg"], 3)

    glows, acc = [], np.zeros_like(bg)
    for c in L["cols"]:
        acc = acc + lens(c)
        e = acc + glow(acc, h, threshold=0.0, strength=0.55)
        glows.append(np.clip(tonemap(e, exposure) * vig, 0, 1))
    return bg_out, gantry, fg, glows


def composite(bg, gantry, glow_k, fg):
    """What the browser shows: normal-over for RGBA layers, screen blend for the light glow."""
    out = bg.copy()
    a = gantry[..., 3:4]
    out = gantry[..., :3] * a + out * (1 - a)
    if glow_k is not None:
        out = 1 - (1 - out) * (1 - glow_k)
    a = fg[..., 3:4]
    return fg[..., :3] * a + out * (1 - a)


def to8(img):
    return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))


def bbox(mask, pad, w, h):
    ys, xs = np.where(mask)
    return (max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0),
            min(int(xs.max()) + pad + 1, w), min(int(ys.max()) + pad + 1, h))


def export(prefix, variant, assets_dir, manifest_path, exposure, focus, widths):
    L = load(prefix)
    bg, gantry, fg, glows = build_layers(L, exposure)
    h, w, _ = bg.shape
    widths = [w if v == 0 else v for v in widths]

    def save_scaled(img, base, quality, lossless_alpha=False):
        out = []
        for pw in widths:
            name = f"{variant}-{base}-{pw}.webp"
            im = img if pw == w else img.resize((pw, round(h * pw / w)), Image.LANCZOS)
            im.save(f"{assets_dir}/{name}", "WEBP", quality=quality, method=6, exact=lossless_alpha)
            out.append({"file": name, "w": pw})
        return out

    bg_plates = save_scaled(to8(bg), "background", 86)
    fg_plates = save_scaled(to8(fg), "foreground", 88)

    # gantry: crop to its alpha
    gx0, gy0, gx1, gy1 = bbox(gantry[..., 3] > 0.002, 2, w, h)
    gname = f"{variant}-gantry.webp"
    to8(gantry[gy0:gy1, gx0:gx1]).save(f"{assets_dir}/{gname}", "WEBP", quality=90, method=6)

    # light states: crop to where the brightest state's glow is visible
    x0, y0, x1, y1 = bbox(glows[-1].max(axis=-1) > 1.5 / 255, int(0.004 * w), w, h)
    lights = []
    for k, g in enumerate(glows, start=1):
        name = f"{variant}-lights-{k}.webp"
        to8(g[y0:y1, x0:x1]).save(f"{assets_dir}/{name}", "WEBP", quality=92, method=6)
        lights.append(name)

    with open(prefix + "-camera.json") as f:
        camera = json.load(f)
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except FileNotFoundError:
        manifest = {}
    manifest[variant] = {
        "width": w,
        "height": h,
        "focus": focus,
        "camera": camera,
        "background": bg_plates,
        "foreground": fg_plates,
        "gantry": {"x": gx0, "y": gy0, "w": gx1 - gx0, "h": gy1 - gy0, "file": gname},
        "lights": {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "files": lights},
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(variant, "gantry", manifest[variant]["gantry"], "lights", manifest[variant]["lights"])
    to8(composite(bg, gantry, glows[-1], fg)).save(f"{prefix}-preview-on.png")
    to8(composite(bg, gantry, None, fg)).save(f"{prefix}-preview-off.png")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    exposure = float(opts.get("exposure", 0.55))
    if args[0] == "export":
        _, prefix, variant, assets_dir, manifest_path = args
        focus = [float(v) for v in opts.get("focus", "0.5,0.45").split(",")]
        widths = [int(v) for v in opts.get("widths", "0").split(",")]
        export(prefix, variant, assets_dir, manifest_path, exposure, focus, widths)
    elif args[0] == "preview":
        _, prefix, out = args
        bg, gantry, fg, glows = build_layers(load(prefix), exposure)
        to8(composite(bg, gantry, glows[-1], fg)).save(out)
        to8(composite(bg, gantry, None, fg)).save(out.replace(".png", "-off.png"))
        to8(bg).save(out.replace(".png", "-bg.png"))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
