"""
Upscale the reference plate with Real-ESRGAN (RRDBNet), for evaluation against plain resampling.

Weights (BSD-3-Clause, https://github.com/xinntao/Real-ESRGAN/releases):
  RealESRGAN_x4plus.pth (v0.1.0), RealESRGAN_x2plus.pth (v0.2.1)

Usage: python render/upscale.py <in> <out.png> <weights.pth> <scale 2|4> [target_width]
The network output is resampled (Lanczos) to `target_width` when given, e.g. 3840 for 4K.
Runs on CPU in overlapping tiles.
"""

from __future__ import annotations

import sys

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.nn import functional as F


class RDB(nn.Module):
    def __init__(self, nf=64, gc=32):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
        return x5 * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf, gc=32):
        super().__init__()
        self.rdb1, self.rdb2, self.rdb3 = RDB(nf, gc), RDB(nf, gc), RDB(nf, gc)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self, scale, nf=64, nb=23, gc=32):
        super().__init__()
        self.scale = scale
        in_ch = 3 * (4 if scale == 2 else 1)
        self.conv_first = nn.Conv2d(in_ch, nf, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        if self.scale == 2:
            x = F.pixel_unshuffle(x, 2)
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


def run(img, net, scale, tile=192, pad=16):
    x = torch.from_numpy(img).permute(2, 0, 1)[None]
    _, _, h, w = x.shape
    out = torch.zeros(1, 3, h * scale, w * scale)
    for y0 in range(0, h, tile):
        for x0 in range(0, w, tile):
            ys, xs = max(y0 - pad, 0), max(x0 - pad, 0)
            ye, xe = min(y0 + tile + pad, h), min(x0 + tile + pad, w)
            with torch.no_grad():
                o = net(x[:, :, ys:ye, xs:xe])
            oy, ox = (y0 - ys) * scale, (x0 - xs) * scale
            th, tw = min(tile, h - y0) * scale, min(tile, w - x0) * scale
            out[:, :, y0 * scale:y0 * scale + th, x0 * scale:x0 * scale + tw] = o[:, :, oy:oy + th, ox:ox + tw]
            print(f"tile {y0},{x0}", flush=True)
    return out[0].permute(1, 2, 0).clamp(0, 1).numpy()


def main():
    src, dst, weights, scale = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    target_w = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    torch.set_num_threads(4)
    img = np.asarray(Image.open(src).convert("RGB")).astype(np.float32) / 255
    net = RRDBNet(scale)
    sd = torch.load(weights, map_location="cpu")
    net.load_state_dict(sd.get("params_ema", sd.get("params", sd)), strict=True)
    net.eval()
    h, w, _ = img.shape
    # the x2 model unshuffles 2x2 blocks: work on even dimensions (edge-replicated), crop after
    padded = np.pad(img, ((0, h % 2), (0, w % 2), (0, 0)), mode="edge")
    up = run(padded, net, scale)[: h * scale, : w * scale]
    out = Image.fromarray((up * 255 + 0.5).astype(np.uint8))
    if target_w:
        out = out.resize((target_w, round(out.height * target_w / out.width)), Image.LANCZOS)
    out.save(dst)


if __name__ == "__main__":
    main()
