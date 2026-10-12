"""
Post-process a multilayer EXR from scene.py into web assets.

  * plate   = Image pass of the plate render     (all start lights off)
  * state_k = plate + col1 + ... + colk          (k lights lit; columns from the lamps render)
  * atmospheric haze from the Mist pass, bloom, filmic tone curve, vignette, grain
  * writes: <name>.webp / .jpg (lights-off plate) and <name>-lights-k.webp crops for k = 1..5,
    plus <name>.json describing where each crop sits (in plate pixels).

Usage:
  python render/post.py <render prefix> <outdir> <name> --exposure=0.55                (preview PNGs)
  python render/post.py export <render prefix> <variant> <assets dir> <manifest.json> \\
      --exposure=0.55 --focus=0.5,0.45 --widths=0,1440                                 (web assets)
"""

from __future__ import annotations

import json
import sys

import numpy as np
import OpenEXR
from PIL import Image


def read_exr(path):
    with OpenEXR.File(path, separate_channels=True) as f:
        ch = f.channels()
        return np.stack([np.asarray(ch[c].pixels, dtype=np.float32) for c in ("R", "G", "B")], axis=-1)


def load(prefix):
    """<prefix>Image/Mist.exr from the plate pass, <prefix>-lampsCombined_colK.exr from the lamps pass."""
    plate = read_exr(prefix + "Image.exr")
    cols = [np.nan_to_num(read_exr(prefix + f"-lampsCombined_col{k}.exr")) for k in range(1, 6)]
    mz = read_exr(prefix + "Mist.exr")[..., 0]
    return plate, cols, mz


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


def bloom(lin, h):
    bright = np.clip(lin - 1.2, 0, 60)
    s = h / 1000.0
    b = 0.6 * blur(bright, 3 * s) + 0.3 * blur(bright, 12 * s) + 0.18 * blur(bright, 40 * s)
    return lin + b * 0.35


def tonemap(lin, exposure):
    x = lin * exposure
    # ACES-like filmic curve (Narkowicz), applied per channel, then sRGB OETF
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    y = np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
    return np.where(y <= 0.0031308, 12.92 * y, 1.055 * np.power(y, 1 / 2.4) - 0.055)


def lens(img, k1=0.035, ca=0.0006):
    """Mild barrel distortion + lateral chromatic aberration of a wide onboard lens (nearest/bilinear remap)."""
    h, w, _ = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2) / (w / 2)
    ny = (yy - h / 2) / (w / 2)
    r2 = nx * nx + ny * ny
    out = np.empty_like(img)
    for c, extra in enumerate((ca, 0.0, -ca)):
        f = 1 - k1 * r2 * 0.25 + extra * r2  # sample further in at edges -> barrel
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


def finish(lin, mz, exposure, seed=1):
    lin = lens(lin)
    mz = lens(np.repeat(mz[..., None], 3, -1))[..., 0]
    h, w, _ = lin.shape
    haze_col = np.array([0.012, 0.011, 0.012], np.float32)
    k = np.clip(mz, 0, 1)[..., None] * 0.35
    lin = lin * (1 - k) + haze_col * k
    lin = bloom(lin, h)
    out = tonemap(lin, exposure)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    out = out * (1 - 0.28 * np.clip(r - 0.55, 0, 1) ** 1.5)[..., None]
    rng = np.random.default_rng(seed)
    out = out + rng.normal(0, 0.008, size=(h, w, 1)).astype(np.float32)
    return np.clip(out, 0, 1)


def to8(img):
    return Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))


def export(prefix, variant, assets_dir, manifest_path, exposure, focus, plate_widths):
    """Write the web assets for one camera variant and merge its entry into the manifest."""
    plate, cols, mz = load(prefix)
    h, w, _ = plate.shape
    off = finish(plate, mz, exposure)
    states, acc = [], plate.copy()
    for k in range(5):
        acc = acc + cols[k]
        states.append(finish(acc, mz, exposure))
    # region touched by any lit state (lamps + bloom), with a margin
    diff = np.abs(states[-1] - off).max(axis=-1)
    ys, xs = np.where(diff > 1.0 / 255)
    pad = int(0.006 * w)
    x0, x1 = max(int(xs.min()) - pad, 0), min(int(xs.max()) + pad + 1, w)
    y0, y1 = max(int(ys.min()) - pad, 0), min(int(ys.max()) + pad + 1, h)

    img = to8(off)
    plates = []
    for pw in plate_widths:
        name = f"{variant}-{pw}.webp"
        im = img if pw == w else img.resize((pw, round(h * pw / w)), Image.LANCZOS)
        im.save(f"{assets_dir}/{name}", "WEBP", quality=86, method=6)
        plates.append({"file": name, "w": pw})
    lights = []
    for k, st in enumerate(states, start=1):
        name = f"{variant}-lights-{k}.webp"
        to8(st[y0:y1, x0:x1]).save(f"{assets_dir}/{name}", "WEBP", quality=92, method=6)
        lights.append(name)
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except FileNotFoundError:
        manifest = {}
    manifest[variant] = {
        "width": w,
        "height": h,
        "focus": focus,
        "plates": plates,
        "lights": {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "files": lights},
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print(variant, manifest[variant]["lights"])
    # full-frame previews for review
    to8(states[-1]).save(f"{prefix}-preview-on.png")
    img.save(f"{prefix}-preview-off.png")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    exposure = float(opts.get("exposure", 1.0))
    if "export" in sys.argv[1:2]:
        # post.py export <render prefix> <variant> <assets dir> <manifest.json> --focus=0.5,0.45 --widths=2400,1440
        _, prefix, variant, assets_dir, manifest_path = args
        focus = [float(v) for v in opts.get("focus", "0.5,0.45").split(",")]
        widths = [int(v) for v in opts.get("widths", "0").split(",")]
        comb_w = read_exr(prefix + "Image.exr").shape[1]
        widths = [comb_w if v == 0 else v for v in widths]
        export(prefix, variant, assets_dir, manifest_path, exposure, focus, widths)
        return
    # preview: post.py <render prefix> <outdir> <name> [--exposure=..]
    src, outdir, name = args
    plate, cols, mz = load(src)
    to8(finish(plate, mz, exposure)).save(f"{outdir}/{name}.png")
    to8(finish(plate + sum(cols), mz, exposure)).save(f"{outdir}/{name}-on.png")


if __name__ == "__main__":
    main()
