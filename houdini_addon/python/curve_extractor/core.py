# Curve Extractor — DCC shared core (single-image OF, aligned with web v1.4.25)
# Internal distribution only. Do not publish this file or the add-on zips.

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

VERSION = "v1.4.26"
WEB_ALG_VERSION = "v1.4.25"

# Image-space polylines are (row, col) = (y, x), same as the HTML tool.


@dataclass
class ExtractParams:
    hue_min: float = 0.05
    hue_max: float = 0.17
    sat_min: float = 0.25
    val_min: float = 0.25
    bright_thresh: float = 0.70
    bright_layer: float = 0.30
    close_radius: int = 3
    dilate_radius: int = 1
    min_object_size: int = 100
    min_length: int = 30
    rdp_epsilon: float = 8.0
    num_samples: int = 800
    branch_detail: float = 40.0
    branch_attach: float = 70.0
    growth_axis: float = 50.0
    root_y_ratio: float = 0.72
    center_y_ratio: float = 0.65
    invert_mask: bool = False
    auto_invert: bool = True
    line_enhance: bool = True
    bg_enabled: bool = True
    bg_tol: float = 60.0
    prune_length: int = 13
    apply_auto_adapt: bool = True
    trust_top: float = 0.0
    tri_rectify: bool = True
    tri_align_ink: bool = True


@dataclass
class CardParams:
    count: int = 2
    width: float = 24.0
    taper: float = 0.15
    cross_angle: float = 90.0


@dataclass
class ExtractedCurve:
    key: str
    name: str
    points_yx: np.ndarray
    points3d: np.ndarray
    level: int
    color_rgb: Tuple[int, int, int]


@dataclass
class ExtractResult:
    version: str = VERSION
    img_w: int = 0
    img_h: int = 0
    line_drawing: bool = False
    curves: List[ExtractedCurve] = field(default_factory=list)
    card: CardParams = field(default_factory=CardParams)
    of_cache: Any = field(default=None, repr=False)

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "version": WEB_ALG_VERSION,
            "dcc_version": VERSION,
            "tool": "Curve Extractor",
            "imgW": self.img_w,
            "imgH": self.img_h,
            "lineDrawing": self.line_drawing,
            "depthRange": self.img_w * 0.35,
            "coord": {
                "html_world": "x=right, y=image-down, z=forward",
                "yup": "OBJ/UE/Houdini: (x, -y, z)",
                "blender_zup": "(x, z, -y)",
            },
            "card": asdict(self.card),
            "curve_count": len(self.curves),
            "curves": [
                {
                    "key": c.key,
                    "name": c.name,
                    "level": c.level,
                    "color": list(c.color_rgb),
                    "point_count": int(len(c.points_yx)),
                    "points": [[float(p[1]), float(p[0])] for p in c.points_yx],
                    "points3d": [[float(p[0]), float(p[1]), float(p[2])] for p in c.points3d],
                    "points3d_yup": [
                        [float(p[0]), float(-p[1]), float(p[2])] for p in c.points3d
                    ],
                }
                for c in self.curves
            ],
        }


def html_world_to_zup(x: float, y: float, z: float) -> Tuple[float, float, float]:
    return (x, z, -y)


def html_world_to_yup(x: float, y: float, z: float) -> Tuple[float, float, float]:
    return (x, -y, z)


def load_rgb_u8(path: str) -> np.ndarray:
    """Load an 8-bit RGB image as (H, W, 3) uint8. Tries PIL, then imageio, then PNG."""
    try:
        from PIL import Image

        im = Image.open(path).convert("RGB")
        return np.asarray(im, dtype=np.uint8)
    except Exception:
        pass
    try:
        import imageio.v2 as imageio

        arr = np.asarray(imageio.imread(path))
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        return arr[..., :3].astype(np.uint8)
    except Exception:
        pass
    if str(path).lower().endswith(".png"):
        return _load_png_rgb(path)
    raise RuntimeError(
        "Cannot load image. Install Pillow in this DCC Python, or use PNG."
    )


def _load_png_rgb(path: str) -> np.ndarray:
    import struct
    import zlib

    with open(path, "rb") as f:
        raw = f.read()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Not a PNG file")
    pos = 8
    w = h = None
    bit_depth = color_type = None
    idat = []
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        data = raw[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            w, h, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat.append(data)
        elif ctype == b"IEND":
            break
    if w is None or bit_depth != 8 or color_type not in (2, 6):
        raise RuntimeError("Only 8-bit RGB/RGBA PNG is supported without Pillow")
    bp = 3 if color_type == 2 else 4
    dec = zlib.decompress(b"".join(idat))
    stride = 1 + w * bp
    rows = []
    prev = np.zeros(w * bp, dtype=np.uint8)
    for y in range(h):
        filt = dec[y * stride]
        scan = np.frombuffer(dec[y * stride + 1 : (y + 1) * stride], dtype=np.uint8).copy()
        recon = _paeth_unfilter(filt, scan, prev, bp)
        prev = recon
        pix = recon.reshape(w, bp)[:, :3]
        rows.append(pix)
    return np.stack(rows, axis=0)


def _paeth_unfilter(filt: int, scan: np.ndarray, prev: np.ndarray, bp: int) -> np.ndarray:
    out = scan.astype(np.int32)
    if filt == 0:
        return scan
    if filt == 1:
        for i in range(len(out)):
            left = out[i - bp] if i >= bp else 0
            out[i] = (out[i] + left) & 255
        return out.astype(np.uint8)
    if filt == 2:
        return ((out + prev.astype(np.int32)) & 255).astype(np.uint8)
    if filt == 3:
        for i in range(len(out)):
            left = out[i - bp] if i >= bp else 0
            up = int(prev[i])
            out[i] = (out[i] + ((left + up) // 2)) & 255
        return out.astype(np.uint8)
    if filt == 4:
        for i in range(len(out)):
            a = out[i - bp] if i >= bp else 0
            b = int(prev[i])
            c = int(prev[i - bp]) if i >= bp else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            out[i] = (out[i] + pr) & 255
        return out.astype(np.uint8)
    raise RuntimeError("Unsupported PNG filter %s" % filt)


def rgb2hsv(r: np.ndarray, g: np.ndarray, b: np.ndarray):
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    d = mx - mn
    h = np.zeros_like(mx)
    mask = d > 1e-8
    eq_r = mask & (mx == r)
    eq_g = mask & (mx == g) & ~eq_r
    eq_b = mask & ~(eq_r | eq_g)
    h[eq_r] = np.mod((g[eq_r] - b[eq_r]) / d[eq_r], 6.0)
    h[eq_g] = (b[eq_g] - r[eq_g]) / d[eq_g] + 2.0
    h[eq_b] = (r[eq_b] - g[eq_b]) / d[eq_b] + 4.0
    h = h / 6.0
    h = np.where(h < 0, h + 1.0, h)
    s = np.where(mx > 1e-8, d / np.maximum(mx, 1e-8), 0.0)
    return h, s, mx


def apply_fine_mode(p: ExtractParams) -> ExtractParams:
    """Same preset as the HTML「精细模式」button."""
    q = ExtractParams(**asdict(p))
    q.branch_detail = 75
    q.branch_attach = 80
    q.close_radius = 4
    q.dilate_radius = 1
    q.min_object_size = 200
    q.prune_length = 12
    q.min_length = 40
    q.bright_layer = 0.32
    q.rdp_epsilon = 7
    return q


def detect_invert_mask(rgb: np.ndarray) -> bool:
    val = rgb.max(axis=2).astype(np.float64) / 255.0
    return float(val.mean()) > 0.5


def _color_dist(r1, g1, b1, r2, g2, b2) -> float:
    rm = (r1 + r2) / 2.0
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    return math.sqrt((2 + rm / 256.0) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256.0) * db * db)


def estimate_background_color(rgb: np.ndarray):
    h, w = rgb.shape[:2]
    step = max(1, int(round(min(w, h) / 200)))
    samples = []
    samples.extend(rgb[0, ::step].tolist())
    samples.extend(rgb[h - 1, ::step].tolist())
    samples.extend(rgb[::step, 0].tolist())
    samples.extend(rgb[::step, w - 1].tolist())
    arr = np.asarray(samples, dtype=np.float64)
    return [float(np.median(arr[:, 0])), float(np.median(arr[:, 1])), float(np.median(arr[:, 2]))]


def build_background_mask(rgb: np.ndarray, p: ExtractParams) -> np.ndarray:
    h, w = rgb.shape[:2]
    br, bg, bb = estimate_background_color(rgb)
    bg_val = max(br, bg, bb) / 255.0
    tol = p.bg_tol
    local_tol = tol * 0.5
    hue, sat, val = rgb2hsv(rgb[..., 0] / 255.0, rgb[..., 1] / 255.0, rgb[..., 2] / 255.0)
    golden = (hue >= p.hue_min) & (hue <= p.hue_max) & (sat >= p.sat_min) & (val >= p.val_min)
    much_brighter = val > bg_val + 0.22
    is_fg = golden | much_brighter
    bg_mask = np.zeros((h, w), dtype=np.uint8)
    queue = []
    def seed(x, y):
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        if bg_mask[y, x] or is_fg[y, x]:
            return
        r, g, b = [float(v) for v in rgb[y, x]]
        if _color_dist(r, g, b, br, bg, bb) <= tol:
            bg_mask[y, x] = 1
            queue.append((y, x))
    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)
    qh = 0
    while qh < len(queue):
        y, x = queue[qh]
        qh += 1
        cr, cg, cb = [float(v) for v in rgb[y, x]]
        for ny, nx in ((y, x + 1), (y, x - 1), (y + 1, x), (y - 1, x)):
            if ny < 0 or nx < 0 or ny >= h or nx >= w:
                continue
            if bg_mask[ny, nx] or is_fg[ny, nx]:
                continue
            r, g, b = [float(v) for v in rgb[ny, nx]]
            if _color_dist(r, g, b, cr, cg, cb) <= local_tol or _color_dist(r, g, b, br, bg, bb) <= tol:
                bg_mask[ny, nx] = 1
                queue.append((ny, nx))
    return bg_mask


def detect_line_drawing(rgb: np.ndarray) -> bool:
    mx = rgb.max(axis=2)
    dark = mx < 18
    fg = ~dark
    n = rgb.size // 3
    dark_ratio = float(dark.mean())
    if not fg.any():
        return False
    mn = rgb.min(axis=2)
    sat = np.zeros(mx.shape, dtype=np.float64)
    sat[fg] = (mx[fg].astype(np.float64) - mn[fg]) / np.maximum(mx[fg], 1)
    mean_sat = float(sat[fg].mean())
    return dark_ratio > 0.90 and mean_sat < 0.20 and int(fg.sum()) > 200


def branch_detail_cfg(p: ExtractParams) -> Dict[str, float]:
    t = max(0.0, min(1.0, p.branch_detail / 100.0))
    return {
        "t": t,
        "max_curves": int(round(6 + t * 42)),
        "min_length": int(round(110 * (1 - t) + 18 * t)),
        "tube_r": max(1, int(round(4 * (1 - t) + 1 * t))),
        "bundle_gap": 0.058 * (1 - t) + 0.016 * t,
        "keep_min": int(round(28 * (1 - t) + 12 * t)),
    }


def growth_axis_cfg(p: ExtractParams, w: int, h: int) -> Dict[str, Any]:
    t = max(0.0, min(1.0, p.growth_axis / 100.0))
    if t < 0.4:
        horizontal = True
    elif t > 0.6:
        horizontal = False
    else:
        horizontal = w > h * 1.15
    return {"t": t, "horizontal": horizontal}


def branch_attach_cfg(p: ExtractParams, w: int, h: int) -> Dict[str, Any]:
    t = max(0.0, min(1.0, p.branch_attach / 100.0))
    min_dim = min(w, h)
    return {
        "t": t,
        "max_graft": max(8, int(round(min_dim * (0.025 + 0.20 * t)))),
        "walk_steps": int(round(16 + 110 * t)),
        "force": t >= 0.82,
    }


def _disk_offsets(radius: int) -> List[Tuple[int, int]]:
    r = max(0, int(radius))
    out = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out.append((dy, dx))
    return out


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    h, w = mask.shape
    src = mask.astype(bool)
    out = src.copy()
    for dy, dx in _disk_offsets(radius):
        ys = slice(max(0, dy), h + min(0, dy))
        xs = slice(max(0, dx), w + min(0, dx))
        sy = slice(max(0, -dy), h - max(0, dy))
        sx = slice(max(0, -dx), w - max(0, dx))
        out[ys, xs] |= src[sy, sx]
    return out.astype(np.uint8)


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    h, w = mask.shape
    src = mask.astype(bool)
    out = np.ones((h, w), dtype=bool)
    for dy, dx in _disk_offsets(radius):
        ys = slice(max(0, dy), h + min(0, dy))
        xs = slice(max(0, dx), w + min(0, dx))
        sy = slice(max(0, -dy), h - max(0, dy))
        sx = slice(max(0, -dx), w - max(0, dx))
        chunk = np.zeros((h, w), dtype=bool)
        chunk[ys, xs] = src[sy, sx]
        out &= chunk
        if dy != 0:
            if dy > 0:
                out[:dy, :] = False
            else:
                out[h + dy :, :] = False
        if dx != 0:
            if dx > 0:
                out[:, :dx] = False
            else:
                out[:, w + dx :] = False
    return out.astype(np.uint8)


def _close(mask: np.ndarray, radius: int) -> np.ndarray:
    return _erode(_dilate(mask, radius), radius)


def _remove_small(mask: np.ndarray, min_size: int) -> np.ndarray:
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=np.uint8)
    out = np.zeros((h, w), dtype=np.uint8)
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if visited[y0, x0]:
            continue
        stack = [(y0, x0)]
        visited[y0, x0] = 1
        comp = []
        while stack:
            y, x = stack.pop()
            comp.append((y, x))
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = 1
                    stack.append((ny, nx))
        if len(comp) >= min_size:
            for y, x in comp:
                out[y, x] = 1
    return out


def extract_mask(rgb: np.ndarray, p: ExtractParams, line_drawing: bool,
                 bg_mask: Optional[np.ndarray] = None):
    h, w = rgb.shape[:2]
    rf = rgb[..., 0].astype(np.float64) / 255.0
    gf = rgb[..., 1].astype(np.float64) / 255.0
    bf = rgb[..., 2].astype(np.float64) / 255.0
    hue, sat, val = rgb2hsv(rf, gf, bf)
    brightness = val.copy()
    if line_drawing:
        thresh = min(p.bright_thresh, 0.22)
        mask = (val >= thresh).astype(np.uint8)
    else:
        hue_m = (hue >= p.hue_min) & (hue <= p.hue_max)
        sat_m = sat >= p.sat_min
        val_m = val >= p.val_min
        bright_m = val >= p.bright_thresh
        layer_m = val >= p.bright_layer
        mask = (((hue_m & sat_m & val_m) | bright_m) & layer_m).astype(np.uint8)
    if p.invert_mask:
        mask = (1 - mask).astype(np.uint8)
    if (not line_drawing) and bg_mask is not None:
        mask = np.where(bg_mask, 0, mask).astype(np.uint8)
    return mask, brightness


def auto_adapt(mask: np.ndarray, p: ExtractParams, line_drawing: bool) -> ExtractParams:
    h, w = mask.shape
    q = ExtractParams(**asdict(p))
    if not p.apply_auto_adapt:
        return q
    visited = np.zeros((h, w), dtype=np.uint8)
    sizes = []
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if visited[y0, x0]:
            continue
        stack = [(y0, x0)]
        visited[y0, x0] = 1
        size = 0
        while stack:
            y, x = stack.pop()
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = 1
                        stack.append((ny, nx))
        sizes.append(size)
    ncomp = len(sizes)
    scale = max(w, h) / 1000.0
    if line_drawing:
        q.close_radius = max(1, int(round(1 * scale)))
        q.dilate_radius = 0
        q.min_object_size = max(20, int(round(30 * scale)))
        q.prune_length = max(8, int(round(10 * scale)))
        q.rdp_epsilon = 1.5
    elif ncomp <= 3:
        q.close_radius = max(1, int(round(2 * scale)))
        q.dilate_radius = 0
        q.min_object_size = int(round(50 * scale))
        q.prune_length = max(3, int(round(5 * scale)))
    elif ncomp <= 15:
        q.close_radius = max(2, int(round(3 * scale)))
        q.dilate_radius = 0
        q.min_object_size = int(round(80 * scale))
        q.prune_length = max(5, int(round(8 * scale)))
    else:
        q.close_radius = max(3, int(round(4 * scale)))
        q.dilate_radius = 1
        q.min_object_size = int(round(60 * scale))
        q.prune_length = max(5, int(round(8 * scale)))
    return q


def solidify(mask: np.ndarray, p: ExtractParams, line_drawing: bool) -> np.ndarray:
    result = mask
    if not line_drawing:
        result = _remove_small(result, p.min_object_size)
    if p.close_radius > 0:
        result = _close(result, p.close_radius)
    if p.dilate_radius > 0:
        result = _dilate(result, p.dilate_radius)
    result = _remove_small(
        result, p.min_object_size if line_drawing else p.min_object_size * 2
    )
    return result


def _gaussian_kernel1d(sigma: float, radius: int) -> np.ndarray:
    xs = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-(xs * xs) / (2 * sigma * sigma))
    return k / k.sum()


def _conv1d_axis(img: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    r = len(kernel) // 2
    padded = np.pad(img, ((r, r), (r, r)) if img.ndim == 2 else r, mode="edge")
    out = np.zeros_like(img, dtype=np.float64)
    if axis == 1:
        for i, k in enumerate(kernel):
            out += k * padded[r:-r, i : i + img.shape[1]]
    else:
        for i, k in enumerate(kernel):
            out += k * padded[i : i + img.shape[0], r:-r]
    return out


def compute_orientation_field(brightness: np.ndarray, mask: np.ndarray):
    h, w = brightness.shape
    padded = np.pad(brightness, 1, mode="edge")
    gx = (
        padded[:-2, 2:]
        + 2 * padded[1:-1, 2:]
        + padded[2:, 2:]
        - (padded[:-2, :-2] + 2 * padded[1:-1, :-2] + padded[2:, :-2])
    )
    gy = (
        padded[2:, :-2]
        + 2 * padded[2:, 1:-1]
        + padded[2:, 2:]
        - (padded[:-2, :-2] + 2 * padded[:-2, 1:-1] + padded[:-2, 2:])
    )
    gx *= mask
    gy *= mask
    raw_jxx, raw_jyy, raw_jxy = gx * gx, gy * gy, gx * gy
    k = _gaussian_kernel1d(1.5, 3)
    jxx = _conv1d_axis(_conv1d_axis(raw_jxx, k, 1), k, 0)
    jyy = _conv1d_axis(_conv1d_axis(raw_jyy, k, 1), k, 0)
    jxy = _conv1d_axis(_conv1d_axis(raw_jxy, k, 1), k, 0)
    jxx *= mask
    jyy *= mask
    jxy *= mask
    tr = jxx + jyy
    det = jxx * jyy - jxy * jxy
    disc = np.sqrt(np.maximum(0.0, tr * tr / 4.0 - det))
    lambda2 = tr / 2.0 - disc
    vx = np.where(np.abs(jxy) > 1e-10, jxy, np.where(jxx <= jyy, 1.0, 0.0))
    vy = np.where(np.abs(jxy) > 1e-10, lambda2 - jxx, np.where(jxx <= jyy, 0.0, 1.0))
    mag = np.sqrt(vx * vx + vy * vy)
    mag = np.where(mag < 1e-12, 1.0, mag)
    dir_x = (vx / mag) * mask
    dir_y = (vy / mag) * mask
    lam_sum = tr
    lam_diff = 2.0 * disc
    coherence = np.divide(lam_diff, lam_sum, out=np.zeros_like(lam_sum), where=lam_sum > 0) * mask
    return dir_x, dir_y, coherence


def _stamp_tube(visited: np.ndarray, path: Sequence[Sequence[float]], radius: int):
    h, w = visited.shape
    r = max(0, int(radius))
    for y, x in path:
        iy, ix = int(round(y)), int(round(x))
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy > r * r:
                    continue
                ny, nx = iy + dy, ix + dx
                if 0 <= ny < h and 0 <= nx < w:
                    visited[ny, nx] = 1


def trace_orientation_field(
    brightness: np.ndarray,
    mask: np.ndarray,
    dir_x: np.ndarray,
    dir_y: np.ndarray,
    coherence: np.ndarray,
    seed_x: float,
    seed_y: float,
    invert_mask: bool,
    line_drawing: bool,
    visited: np.ndarray,
    tube_r: int,
    visit_hits_limit: int,
) -> List[List[float]]:
    h, w = brightness.shape
    step_size = 2.0
    max_steps = 6000
    max_gap = 16 if line_drawing else 12
    ema_alpha = 0.1 if line_drawing else 0.12
    half: List[List[List[float]]] = [[], []]

    for d, direction in enumerate((1, -1)):
        cx, cy = float(seed_x), float(seed_y)
        sdx = sdy = 0.0
        local = set()
        hits = 0
        gap = 0
        for step in range(max_steps):
            ix, iy = int(round(cx)), int(round(cy))
            if ix < 1 or ix >= w - 1 or iy < 1 or iy >= h - 1:
                break
            if not mask[iy, ix]:
                gap += 1
                if gap > max_gap:
                    break
                if sdx == 0 and sdy == 0:
                    break
                cx += sdx * direction * step_size
                cy += sdy * direction * step_size
                continue
            gap = 0
            bval = 1.0 - brightness[iy, ix] if invert_mask else brightness[iy, ix]
            if bval < 0.08:
                gap += 1
                if gap > max_gap:
                    break
                if sdx == 0 and sdy == 0:
                    break
                cx += sdx * direction * step_size
                cy += sdy * direction * step_size
                continue
            if step > 5 and visited[iy, ix]:
                hits += 1
                if hits > visit_hits_limit:
                    break
            else:
                hits = max(0, hits - 1)
            idx = iy * w + ix
            if idx in local:
                break
            local.add(idx)
            half[d].append([float(iy), float(ix)])

            x0, y0 = int(math.floor(cx)), int(math.floor(cy))
            fx, fy = cx - x0, cy - y0
            if x0 < 0 or y0 < 0 or x0 >= w - 1 or y0 >= h - 1:
                break
            dx = (
                (1 - fx) * (1 - fy) * dir_x[y0, x0]
                + fx * (1 - fy) * dir_x[y0, x0 + 1]
                + (1 - fx) * fy * dir_x[y0 + 1, x0]
                + fx * fy * dir_x[y0 + 1, x0 + 1]
            )
            dy = (
                (1 - fx) * (1 - fy) * dir_y[y0, x0]
                + fx * (1 - fy) * dir_y[y0, x0 + 1]
                + (1 - fx) * fy * dir_y[y0 + 1, x0]
                + fx * fy * dir_y[y0 + 1, x0 + 1]
            )
            mag = math.hypot(dx, dy)
            if mag < 0.01:
                if sdx == 0 and sdy == 0:
                    break
                cx += sdx * direction * step_size
                cy += sdy * direction * step_size
                continue
            dx /= mag
            dy /= mag
            if sdx != 0 or sdy != 0:
                if dx * sdx + dy * sdy < 0:
                    dx, dy = -dx, -dy
            if sdx == 0 and sdy == 0:
                sdx, sdy = dx, dy
            elif line_drawing:
                coh = float(coherence[iy, ix])
                headings = [(sdx, sdy)]
                if coh > 0.35 and (dx * sdx + dy * sdy) > 0.25:
                    headings.append((dx, dy))
                for ang in (0.18, -0.18, 0.4, -0.4):
                    ca, sa = math.cos(ang), math.sin(ang)
                    headings.append((sdx * ca - sdy * sa, sdx * sa + sdy * ca))
                best_dx, best_dy, best_sc = sdx, sdy, -1e9
                for hx, hy in headings:
                    hm = math.hypot(hx, hy) or 1.0
                    hx, hy = hx / hm, hy / hm
                    sc = 0.3 * (hx * sdx + hy * sdy)
                    for ahead in range(2, 11, 2):
                        ax = int(round(cx + hx * ahead * direction))
                        ay = int(round(cy + hy * ahead * direction))
                        if ax < 1 or ax >= w - 1 or ay < 1 or ay >= h - 1:
                            sc -= 0.4
                            continue
                        if mask[ay, ax]:
                            bv = 1.0 - brightness[ay, ax] if invert_mask else brightness[ay, ax]
                            sc += bv * (1.15 - ahead * 0.04)
                        else:
                            sc -= 0.5
                    if sc > best_sc:
                        best_sc = sc
                        best_dx, best_dy = hx, hy
                stick = 0.9 if coh < 0.42 else 0.7
                ndx = best_dx * (1 - stick) + sdx * stick
                ndy = best_dy * (1 - stick) + sdy * stick
                nmag = math.hypot(ndx, ndy) or 1.0
                sdx, sdy = ndx / nmag, ndy / nmag
            else:
                coh = float(coherence[iy, ix] or 0.5)
                stick = 0.72
                if dx * sdx + dy * sdy >= 0.2:
                    alpha = ema_alpha + coh * 0.2
                    ndx = sdx * (1 - alpha) + dx * alpha
                    ndy = sdy * (1 - alpha) + dy * alpha
                    ndx = ndx * (1 - stick) + sdx * stick
                    ndy = ndy * (1 - stick) + sdy * stick
                    smag = math.hypot(ndx, ndy) or 1.0
                    sdx, sdy = ndx / smag, ndy / smag
            cx += sdx * direction * step_size
            cy += sdy * direction * step_size

    path = list(reversed(half[1])) + half[0]
    _stamp_tube(visited, path, 1 if line_drawing else tube_r)
    return path


def _mean_nearest(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]], step: int) -> float:
    if not a or not b:
        return 1e9
    bb = np.asarray(b, dtype=np.float64)
    acc = 0.0
    n = 0
    for i in range(0, len(a), max(1, step)):
        d = np.hypot(bb[:, 0] - a[i][0], bb[:, 1] - a[i][1]).min()
        acc += float(d)
        n += 1
    return acc / max(1, n)


def bundle_overdrawn(curves: List[List[List[float]]], w: int, h: int, gap_scale: float):
    if len(curves) < 2:
        return curves
    used = [False] * len(curves)
    order = sorted(range(len(curves)), key=lambda i: -len(curves[i]))
    thresh = max(16.0, min(w, h) * (gap_scale or 0.028))
    out = []
    for i in order:
        if used[i]:
            continue
        group = [curves[i]]
        used[i] = True
        for j in order:
            if used[j]:
                continue
            d12 = _mean_nearest(curves[i], curves[j], 5)
            d21 = _mean_nearest(curves[j], curves[i], 5)
            if min(d12, d21) < thresh and max(d12, d21) < thresh * 2.4:
                group.append(curves[j])
                used[j] = True
        if len(group) == 1:
            out.append(group[0])
        else:
            out.append(_merge_stroke_bundle(group))
    return out


def _merge_stroke_bundle(group):
    spine = max(group, key=len)
    r2 = 16 * 16
    out = []
    for i, sp in enumerate(spine):
        sy, sx, n = sp[0], sp[1], 1
        t = i / (len(spine) - 1) if len(spine) > 1 else 0
        for c in group:
            if c is spine:
                continue
            j0 = int(round(t * (len(c) - 1)))
            lo, hi = max(0, j0 - 24), min(len(c) - 1, j0 + 24)
            best, by, bx = r2 + 1, 0.0, 0.0
            for j in range(lo, hi + 1):
                dy = c[j][0] - spine[i][0]
                dx = c[j][1] - spine[i][1]
                d = dy * dy + dx * dx
                if d < best:
                    best, by, bx = d, c[j][0], c[j][1]
            if best <= r2:
                sy += by
                sx += bx
                n += 1
        out.append([sy / n, sx / n])
    return out


def open_false_loop(pts):
    if not pts or len(pts) < 16:
        return pts
    a, b = pts[0], pts[-1]
    if math.hypot(a[0] - b[0], a[1] - b[1]) > 14:
        return pts
    ymin = min(p[0] for p in pts)
    ymax = max(p[0] for p in pts)
    xmin = min(p[1] for p in pts)
    xmax = max(p[1] for p in pts)
    box = max(1, xmax - xmin) + max(1, ymax - ymin)
    if len(pts) > box * 2.2:
        return pts[: len(pts) // 2]
    return pts


def _seg_intersect(a, b, c, d):
    def cross(p, q, r):
        return (q[1] - p[1]) * (r[0] - p[0]) - (q[0] - p[0]) * (r[1] - p[1])
    d1, d2 = cross(a, b, c), cross(a, b, d)
    d3, d4 = cross(c, d, a), cross(c, d, b)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return False


def split_crossing_polyline(pts):
    if not pts or len(pts) < 12:
        return [pts]
    n = len(pts)
    step = max(1, n // 500)
    for i in range(0, n - 3, step):
        for j in range(i + 8, n - 1, step):
            if not _seg_intersect(pts[i], pts[i + 1], pts[j], pts[j + 1]):
                continue
            a = pts[: i + 1] + pts[j + 1 :]
            b = pts[i : j + 1]
            out = []
            if len(a) >= 8:
                out.append(a)
            if len(b) >= 8:
                out.append(b)
            return out or [pts]
    return [pts]


def sanitize_line_art(curves):
    out = []
    for c in curves:
        for p in split_crossing_polyline(open_false_loop(c)):
            if p and len(p) >= 24:
                out.append(p)
    return out


def filter_label_curves(curves, w, h):
    kept = []
    for pts in curves:
        ymin = min(p[0] for p in pts)
        ymax = max(p[0] for p in pts)
        xmin = min(p[1] for p in pts)
        xmax = max(p[1] for p in pts)
        y_mid = (ymin + ymax) / (2 * h)
        x_mid = (xmin + xmax) / (2 * w)
        y_span = (ymax - ymin) / h
        if y_mid < 0.12 and y_span < 0.08 and x_mid < 0.6:
            continue
        kept.append(pts)
    return kept


def deduplicate_curves(curves, brightness, w, h, min_dist=8):
    if len(curves) <= 1:
        return curves
    avg_b = []
    for curve in curves:
        s = c = 0.0
        for pt in curve:
            y, x = int(math.floor(pt[0])), int(math.floor(pt[1]))
            if 0 <= y < h and 0 <= x < w and brightness is not None:
                s += float(brightness[y, x])
                c += 1
        avg_b.append(s / c if c else 0.5)
    order = sorted(range(len(curves)), key=lambda i: -avg_b[i])
    kept, kept_pts = [], []
    for ci in order:
        curve = curves[ci]
        samples = [curve[i] for i in range(0, len(curve), 3)]
        too_close = False
        for kps in kept_pts:
            close = 0
            check = min(len(samples), 30)
            for si in range(check):
                s = samples[int(si * len(samples) / check)]
                for kp in kps:
                    if (s[0] - kp[0]) ** 2 + (s[1] - kp[1]) ** 2 < min_dist * min_dist:
                        close += 1
                        break
            if check and close / check > 0.6:
                too_close = True
                break
        if not too_close:
            kept.append(curve)
            kept_pts.append(samples[::2])
    return kept


def _travel_dir(curve, end: int):
    n = min(10, len(curve) - 1)
    if n < 1:
        return (1.0, 0.0)
    if end == 1:
        p0, p1 = curve[-1 - n], curve[-1]
    else:
        p0, p1 = curve[0], curve[n]
    dx, dy = p1[1] - p0[1], p1[0] - p0[0]
    mag = math.hypot(dx, dy) or 1.0
    return (dx / mag, dy / mag)


def connect_segments(curves, w, h, line_drawing: bool, horizontal: bool):
    if len(curves) <= 1:
        return curves
    if line_drawing:
        max_dist = max(40, int(round(min(w, h) / 25)))
        min_dot = math.cos(math.pi / 3)
    elif horizontal:
        max_dist = max(28, int(round(min(w, h) / 28)))
        min_dot = math.cos(math.pi / 3.2)
    else:
        max_dist = max(12, int(round(min(w, h) / 70)))
        min_dot = math.cos(math.pi / 4.5)
    segs = [list(c) for c in curves]
    used = [False] * len(segs)
    order = sorted(range(len(segs)), key=lambda i: -len(segs[i]))
    result = []

    def end_pt(curve, end):
        return curve[-1] if end == 1 else curve[0]

    def try_attach(merged):
        for oj in order:
            if used[oj]:
                continue
            other = segs[oj]
            best = None
            best_dist = max_dist + 1
            for our_end in (0, 1):
                for their_end in (0, 1):
                    a, b = end_pt(merged, our_end), end_pt(other, their_end)
                    dist = math.hypot(a[1] - b[1], a[0] - b[0])
                    if dist > max_dist:
                        continue
                    da = _travel_dir(merged, our_end)
                    db = _travel_dir(other, their_end)
                    if our_end == 0:
                        da = (-da[0], -da[1])
                    if our_end == their_end:
                        db = (-db[0], -db[1])
                    if da[0] * db[0] + da[1] * db[1] < min_dot:
                        continue
                    if dist < best_dist:
                        best_dist = dist
                        best = (our_end, their_end)
            if not best:
                continue
            our_end, their_end = best
            other_use = list(reversed(other)) if our_end == their_end else other
            nxt = merged + other_use if our_end == 1 else other_use + merged
            used[oj] = True
            return nxt, True
        return merged, False

    for ci in order:
        if used[ci]:
            continue
        merged = list(segs[ci])
        used[ci] = True
        changed = True
        while changed:
            merged, changed = try_attach(merged)
        result.append(merged)
    return result


def _polyline_len(pts) -> float:
    L = 0.0
    for i in range(1, len(pts)):
        L += math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    return L


def _nearest_on(pt, curve):
    best_d, best_i = 1e18, 0
    for i, q in enumerate(curve):
        d = math.hypot(pt[0] - q[0], pt[1] - q[1])
        if d < best_d:
            best_d, best_i = d, i
    return best_d, curve[best_i], best_i, best_i / max(1, len(curve) - 1)


def _end_dir(curve, end: int):
    n = min(10, len(curve) - 1)
    if n < 1:
        return (1.0, 0.0)
    if end == 1:
        p0, p1 = curve[-1 - n], curve[-1]
    else:
        p0, p1 = curve[n], curve[0]
    dx, dy = p1[1] - p0[1], p1[0] - p0[0]
    mag = math.hypot(dx, dy) or 1.0
    return (dx / mag, dy / mag)


def _walk_ink(y0, x0, ty, tx, mask, brightness, max_steps):
    h, w = mask.shape
    path = []
    y, x = float(y0), float(x0)
    seen = np.zeros((h, w), dtype=np.uint8)
    sy, sx = int(round(y0)), int(round(x0))
    if 0 <= sy < h and 0 <= sx < w:
        seen[sy, sx] = 1
    for _ in range(max_steps):
        dist = math.hypot(y - ty, x - tx)
        if dist < 2.4:
            path.append([ty, tx])
            break
        best = None
        best_score = 1e18
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = int(round(y + dy)), int(round(x + dx))
                if ny < 1 or nx < 1 or ny >= h - 1 or nx >= w - 1:
                    continue
                if seen[ny, nx]:
                    continue
                on = bool(mask[ny, nx])
                br = float(brightness[ny, nx])
                if not on and br < 0.16:
                    continue
                nd = math.hypot(ny - ty, nx - tx)
                if nd > dist + 1.15:
                    continue
                score = nd - (1.4 if on else 0) - br * 0.9
                if score < best_score:
                    best_score = score
                    best = (ny, nx)
        if best is None:
            break
        seen[best] = 1
        path.append([float(best[0]), float(best[1])])
        y, x = best
    return path


def _snap_root(curve, target):
    out = [list(p) for p in curve]
    out[0] = [target[0], target[1]]
    n = min(16, max(5, int(len(out) * 0.14)))
    for _ in range(5):
        b = [list(p) for p in out]
        for i in range(1, min(n, len(out) - 1)):
            wgt = 0.18 if i == n - 1 else 0.46
            b[i][0] = out[i][0] * (1 - wgt) + (out[i - 1][0] + out[i + 1][0]) * 0.5 * wgt
            b[i][1] = out[i][1] * (1 - wgt) + (out[i - 1][1] + out[i + 1][1]) * 0.5 * wgt
        for i in range(1, min(n, len(out) - 1)):
            out[i] = b[i]
    out[0] = [target[0], target[1]]
    return out


def _attach_end(child, end, target, walk_steps, mask, brightness):
    c = list(reversed(child)) if end == 1 else [list(p) for p in child]
    walk = _walk_ink(c[0][0], c[0][1], target[0], target[1], mask, brightness, walk_steps)
    out = [[target[0], target[1]]]
    for q in reversed(walk):
        last = out[-1]
        if math.hypot(q[0] - last[0], q[1] - last[1]) > 0.45:
            out.append(list(q))
    for q in c:
        last = out[-1]
        if math.hypot(q[0] - last[0], q[1] - last[1]) > 0.45:
            out.append(list(q))
    return _snap_root(out, target)


def _pick_attach(child, parents, max_graft, force):
    best = None
    for end in (0, 1):
        pt = child[0] if end == 0 else child[-1]
        inward = _end_dir(child, end)
        for parent in parents:
            d, p, _i, t = _nearest_on(pt, parent)
            if d > max_graft:
                continue
            vx, vy = p[1] - pt[1], p[0] - pt[0]
            vm = math.hypot(vx, vy) or 1.0
            align = (vx * inward[0] + vy * inward[1]) / vm
            if not force and align < -0.55 and t > 0.88:
                continue
            tip = 10 if (t > 0.93 or t < 0.03) else 0
            fold = 14 * (0.2 - align) if align < 0 else 0
            score = d + tip + fold
            if best is None or score < best["score"]:
                best = {"end": end, "p": p, "score": score}
    return best


def graft_curves(curves, w, h, p: ExtractParams, mask, brightness, horizontal: bool):
    if len(curves) < 2 or horizontal:
        return curves
    cfg = branch_attach_cfg(p, w, h)
    if cfg["t"] < 0.03:
        return curves
    cs = [[list(q) for q in c] for c in curves if c and len(c) >= 4]
    order = sorted(range(len(cs)), key=lambda i: -_polyline_len(cs[i]))
    grafted = [False] * len(cs)
    for k in range(1, len(order)):
        i = order[k]
        parents = [cs[order[m]] for m in range(k)]
        best = _pick_attach(cs[i], parents, cfg["max_graft"], cfg["force"])
        if not best:
            continue
        cs[i] = _attach_end(cs[i], best["end"], best["p"], cfg["walk_steps"], mask, brightness)
        grafted[i] = True
    return cs


def _perp_dist(pt, a, b) -> float:
    dx, dy = b[1] - a[1], b[0] - a[0]
    if dx == 0 and dy == 0:
        return math.hypot(pt[1] - a[1], pt[0] - a[0])
    t = ((pt[1] - a[1]) * dx + (pt[0] - a[0]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(pt[1] - (a[1] + t * dx), pt[0] - (a[0] + t * dy))


def rdp_simplify(points, epsilon: float):
    if len(points) < 3:
        return [list(p) for p in points]
    max_d, max_i = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], points[0], points[-1])
        if d > max_d:
            max_d, max_i = d, i
    if max_d > epsilon:
        left = rdp_simplify(points[: max_i + 1], epsilon)
        right = rdp_simplify(points[max_i:], epsilon)
        return left[:-1] + right
    return [list(points[0]), list(points[-1])]


def laplacian_smooth(points, iters: int, lam: float):
    a = [list(p) for p in points]
    for _ in range(iters):
        b = [list(p) for p in a]
        for i in range(1, len(a) - 1):
            b[i][0] = a[i][0] * (1 - lam) + (a[i - 1][0] + a[i + 1][0]) * 0.5 * lam
            b[i][1] = a[i][1] * (1 - lam) + (a[i - 1][1] + a[i + 1][1]) * 0.5 * lam
        a = b
    return a


def resample_polyline(pts, n: int):
    if not pts or len(pts) < 2:
        return [list(p) for p in pts] if pts else []
    n = max(2, int(n))
    acc = [0.0]
    for i in range(1, len(pts)):
        acc.append(acc[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    L = acc[-1] or 1.0
    out = []
    j = 0
    for i in range(n):
        target = L * i / (n - 1)
        while j < len(acc) - 2 and acc[j + 1] < target:
            j += 1
        den = (acc[j + 1] - acc[j]) or 1.0
        a = (target - acc[j]) / den
        out.append(
            [
                pts[j][0] * (1 - a) + pts[j + 1][0] * a,
                pts[j][1] * (1 - a) + pts[j + 1][1] * a,
            ]
        )
    return out


def _cr_point(p0, p1, p2, p3, t: float):
    pts = [{"x": p[1], "y": p[0]} for p in (p0, p1, p2, p3)]
    alpha = 0.5

    def dist_t(ta, a, b):
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        return ta + pow(max(1e-8, dx * dx + dy * dy), alpha * 0.5)

    t0 = 0.0
    t1 = dist_t(t0, pts[0], pts[1])
    t2 = dist_t(t1, pts[1], pts[2])
    t3 = dist_t(t2, pts[2], pts[3])
    tv = t1 + max(0.0, min(1.0, t)) * (t2 - t1)

    def lerp(a, b, ta, tb, tval):
        u = 0.0 if (tb - ta) < 1e-12 else (tval - ta) / (tb - ta)
        return {"x": a["x"] + (b["x"] - a["x"]) * u, "y": a["y"] + (b["y"] - a["y"]) * u}

    a1 = lerp(pts[0], pts[1], t0, t1, tv)
    a2 = lerp(pts[1], pts[2], t1, t2, tv)
    a3 = lerp(pts[2], pts[3], t2, t3, tv)
    b1 = lerp(a1, a2, t0, t2, tv)
    b2 = lerp(a2, a3, t1, t3, tv)
    c = lerp(b1, b2, t1, t2, tv)
    return [c["y"], c["x"]]


def catmull_rom_open(points, num_samples: int):
    if not points or len(points) < 2:
        return [list(p) for p in points] if points else []
    num_samples = max(2, int(num_samples))
    if len(points) == 2:
        return resample_polyline(points, num_samples)
    pts = [list(p) for p in points]
    p = [pts[0]] + pts + [pts[-1]]
    nseg = len(pts) - 1
    out = []
    for s in range(num_samples):
        tt = s / max(1, num_samples - 1) * nseg
        i = min(nseg - 1, int(math.floor(tt)))
        u = tt - i
        out.append(_cr_point(p[i], p[i + 1], p[i + 2], p[i + 3], u))
    out[0] = list(pts[0])
    out[-1] = list(pts[-1])
    return resample_polyline(out, num_samples)


def fit_smooth(points, num_samples: int, epsilon: float, line_drawing: bool):
    if not points or len(points) < 2:
        return [list(p) for p in points] if points else []
    pre = laplacian_smooth(points, 8 if line_drawing else 3, 0.42)
    control = rdp_simplify(pre, max(1.6, epsilon))
    if len(control) < 3:
        return resample_polyline(control if len(control) >= 2 else pre, num_samples)
    return catmull_rom_open(control, num_samples)


def strip_zigzag(pts):
    if not pts or len(pts) < 16:
        return pts
    keep = [list(pts[0])]
    win = 6
    for i in range(1, len(pts)):
        prev = keep[-1]
        dx, dy = pts[i][1] - prev[1], pts[i][0] - prev[0]
        dm = math.hypot(dx, dy)
        if dm < 0.8:
            continue
        if len(keep) >= win + 1:
            a = keep[-win]
            hx, hy = prev[1] - a[1], prev[0] - a[0]
            hm = math.hypot(hx, hy) or 1.0
            if (dx * hx + dy * hy) / (dm * hm) < -0.25 and dm < 18:
                continue
        keep.append(list(pts[i]))
    return keep if len(keep) >= 8 else pts


def sample_curve_color(curve, rgb: np.ndarray):
    h, w = rgb.shape[:2]
    if curve is None or len(curve) < 2:
        return (255, 215, 0)
    step = max(1, len(curve) // 48)
    rs = gs = bs = n = 0.0
    for i in range(0, len(curve), step):
        y, x = int(math.floor(curve[i][0])), int(math.floor(curve[i][1]))
        if 0 <= y < h and 0 <= x < w:
            rs += float(rgb[y, x, 0])
            gs += float(rgb[y, x, 1])
            bs += float(rgb[y, x, 2])
            n += 1
    if not n:
        return (255, 215, 0)
    r, g, b = rs / n, gs / n, bs / n
    mx = max(r, g, b)
    if mx < 28:
        return (255, 215, 0)
    sc = 230.0 / mx
    return (
        int(min(255, r * sc)),
        int(min(255, g * sc)),
        int(min(255, b * sc)),
    )


def classify_curves(curves, rgb: np.ndarray) -> Tuple[List[int], List[Tuple[int, int, int]]]:
    n = len(curves)
    if not n:
        return [], []
    colors = [sample_curve_color(c, rgb) for c in curves]
    hsvs = []
    for r, g, b in colors:
        h, s, v = rgb2hsv(np.array([r / 255]), np.array([g / 255]), np.array([b / 255]))
        hsvs.append((float(h[0]), float(s[0]), float(v[0])))
    mean_sat = sum(x[1] for x in hsvs) / n
    if mean_sat < 0.12 or n == 1:
        return [1] * n, colors

    def hue_dist(a, b):
        d = abs(a - b)
        return min(d, 1 - d)

    cents = [hsvs[0][0], hsvs[n // 2][0], hsvs[n - 1][0]]
    assign = [0] * n
    for _ in range(12):
        for i in range(n):
            best, bd = 0, 1e9
            for k in range(3):
                d = hue_dist(hsvs[i][0], cents[k]) * (0.35 + hsvs[i][1])
                if d < bd:
                    bd, best = d, k
            assign[i] = best
        for k in range(3):
            sx = sy = c = 0.0
            for i in range(n):
                if assign[i] == k:
                    sx += math.cos(hsvs[i][0] * math.pi * 2)
                    sy += math.sin(hsvs[i][0] * math.pi * 2)
                    c += 1
            if not c:
                continue
            ang = math.atan2(sy, sx)
            if ang < 0:
                ang += math.pi * 2
            cents[k] = ang / (math.pi * 2)
    cluster_v = [0.0, 0.0, 0.0]
    cluster_n = [0, 0, 0]
    for i in range(n):
        cluster_v[assign[i]] += hsvs[i][2]
        cluster_n[assign[i]] += 1
    order = sorted([k for k in range(3) if cluster_n[k] > 0], key=lambda k: -(cluster_v[k] / cluster_n[k]))
    mapping = {k: rank + 1 for rank, k in enumerate(order)}
    return [mapping.get(k, 1) for k in assign], colors


def estimate_depths(curves, brightness, w, h, horizontal: bool, invert_mask: bool):
    root_x = w * 0.12 if horizontal else w / 2
    root_y = h * 0.5 if horizontal else h * 0.85
    profiles = []
    for curve in curves:
        n = len(curve)
        root_is_start = (
            curve[0][1] < curve[-1][1] if horizontal else curve[0][0] > curve[-1][0]
        )
        avg_b = 0.5
        if brightness is not None:
            s = c = 0.0
            for pt in curve:
                y, x = int(math.floor(pt[0])), int(math.floor(pt[1]))
                if 0 <= y < h and 0 <= x < w:
                    bv = 1.0 - brightness[y, x] if invert_mask else float(brightness[y, x])
                    s += bv
                    c += 1
            if c:
                avg_b = s / c
        outer = curve[-1] if root_is_start else curve[0]
        angle = math.atan2(outer[1] - root_x, -(outer[0] - root_y))
        base_z = math.sin(angle * 2.5) * 100 + (avg_b - 0.5) * 60
        profile = []
        for j in range(n):
            t = j / max(1, n - 1)
            spread = t * t * (3 - 2 * t)
            profile.append(base_z * spread)
        profiles.append((profile, root_is_start, base_z))
    return profiles


def curves_to_world(curves, profiles, w, h):
    worlds = []
    for idx, curve in enumerate(curves):
        n = len(curve)
        depth_profile, root_is_start, _ = profiles[idx]
        root_pt = curve[0] if root_is_start else curve[-1]
        root_x_norm = (root_pt[1] - w / 2) / (w / 2 if w else 1)
        base_z = root_x_norm * 150 + math.sin(idx * 2.3) * 60
        pts = []
        for pi, p in enumerate(curve):
            t = (pi / (n - 1)) if root_is_start else (1 - pi / (n - 1))
            x = p[1] - w / 2
            y = p[0] - h / 2
            spread = t * t * (3 - 2 * t)
            z = depth_profile[pi] * 1.2 + base_z * spread
            pts.append([x, y, z])
        worlds.append(np.asarray(pts, dtype=np.float64))
    return worlds


def _of_trace_all(rgb, mask, brightness, p, line_drawing, w, h,
                  of_max_curves=None, of_min_bright=None, of_min_len=None):
    """Match extractCurvesOrientationField + the extractAll OF branch."""
    dir_x, dir_y, coherence = compute_orientation_field(brightness, mask.astype(np.float64))
    detail = branch_detail_cfg(p)
    axis = growth_axis_cfg(p, w, h)
    if line_drawing:
        max_curves, min_len = 24, max(40, p.min_length)
        min_bright = 0.06
        tube_r, visit_hits = 1, 120
        seed_step = max(3, int(round(min(w, h) / 420)))
        coh_min = 0.08
        bundle_gap = 0.03
    else:
        max_curves = int(detail["max_curves"])
        min_len = int(detail["min_length"])
        min_bright = p.bright_layer
        tube_r = max(1, int(detail["tube_r"]) - (1 if axis["horizontal"] else 0))
        visit_hits = 160 if axis["horizontal"] else 40
        seed_step = max(4, int(round(min(w, h) / 300)))
        coh_min = 0.15
        bundle_gap = detail["bundle_gap"]
    if of_max_curves is not None:
        max_curves = int(of_max_curves)
    if of_min_bright is not None:
        min_bright = float(of_min_bright)
    if of_min_len is not None:
        min_len = int(of_min_len)

    seeds = []
    for y in range(seed_step, h - seed_step, seed_step):
        for x in range(seed_step, w - seed_step, seed_step):
            if mask[y, x] and brightness[y, x] >= min_bright and coherence[y, x] > coh_min:
                seeds.append((x, y, float(brightness[y, x] * coherence[y, x])))
    seeds.sort(key=lambda s: -s[2])
    visited = np.zeros((h, w), dtype=np.uint8)
    raw = []
    for sx, sy, _ in seeds:
        if len(raw) >= max_curves:
            break
        if visited[sy, sx]:
            continue
        path = trace_orientation_field(
            brightness, mask, dir_x, dir_y, coherence,
            sx, sy, p.invert_mask, line_drawing, visited, tube_r, visit_hits,
        )
        if len(path) >= min_len:
            raw.append(path)

    if line_drawing:
        bundled = bundle_overdrawn(raw, w, h, bundle_gap)
        traces = sanitize_line_art(bundled)
    else:
        bundled = bundle_overdrawn(raw, w, h, bundle_gap)
        cleaned = [strip_zigzag(open_false_loop(c)) for c in bundled]
        cleaned = [c for c in cleaned if c and len(c) >= int(detail["keep_min"])]
        connected = connect_segments(cleaned, w, h, False, axis["horizontal"])
        traces = graft_curves(connected, w, h, p, mask, brightness, axis["horizontal"])

    traces = deduplicate_curves(traces, brightness, w, h, 10 if line_drawing else 6)
    if line_drawing:
        traces = filter_label_curves(traces, w, h)
    cache = {
        "dir_x": dir_x, "dir_y": dir_y, "coherence": coherence,
        "mask": mask, "brightness": brightness, "rgb": rgb,
        "params": p, "line_drawing": line_drawing,
        "tube_r": tube_r, "visit_hits": visit_hits, "w": w, "h": h,
        "raw": traces,
    }
    return traces, cache


def _extract_from_rgb_single(
    rgb: np.ndarray,
    params: Optional[ExtractParams] = None,
    card: Optional[CardParams] = None,
) -> ExtractResult:
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise ValueError("rgb must be HxWx3")
    rgb = rgb[..., :3]
    if rgb.dtype != np.uint8:
        mx = float(np.max(rgb)) if rgb.size else 1.0
        rgb = (np.clip(rgb / (mx if mx > 1.5 else 1.0), 0, 1) * 255).astype(np.uint8)
    p = params or ExtractParams()
    card = card or CardParams()
    h, w = rgb.shape[:2]
    if p.auto_invert and not p.invert_mask:
        p = ExtractParams(**{**asdict(p), "invert_mask": detect_invert_mask(rgb)})
    line_drawing = bool(p.line_enhance and detect_line_drawing(rgb))
    bg_mask = None
    if p.bg_enabled and not line_drawing:
        bg_mask = build_background_mask(rgb, p)
    mask, brightness = extract_mask(rgb, p, line_drawing, bg_mask)
    p = auto_adapt(mask, p, line_drawing)
    # Web still traces on S.mask (HSV), not S.solid. solidify is preview-only for OF.
    traces, cache = _of_trace_all(rgb, mask, brightness, p, line_drawing, w, h)

    n_samp = min(max(p.num_samples, 160), 480 if line_drawing else 600)
    if line_drawing:
        eps = max(2.8, min(p.rdp_epsilon, 7))
    else:
        eps = max(5, p.rdp_epsilon)
    smoothed = [fit_smooth(c, n_samp, eps, line_drawing) for c in traces]
    smoothed = [c for c in smoothed if c and len(c) >= 2]
    axis = growth_axis_cfg(p, w, h)
    levels, colors = classify_curves(smoothed, rgb)
    profiles = estimate_depths(smoothed, brightness, w, h, axis["horizontal"], p.invert_mask)
    worlds = curves_to_world(smoothed, profiles, w, h)

    result = ExtractResult(
        version=VERSION, img_w=w, img_h=h, line_drawing=line_drawing, card=card, of_cache=cache
    )
    for i, pts in enumerate(smoothed):
        result.curves.append(
            ExtractedCurve(
                key="curve_%02d" % (i + 1),
                name="Curve %02d" % (i + 1),
                points_yx=np.asarray(pts, dtype=np.float64),
                points3d=worlds[i],
                level=levels[i] if i < len(levels) else 1,
                color_rgb=colors[i] if i < len(colors) else (255, 215, 0),
            )
        )
    return result


def pick_stroke(result: ExtractResult, img_x: float, img_y: float) -> ExtractResult:
    """HTML「点选补一笔」: seed OF at the clicked ink pixel."""
    cache = result.of_cache
    if not cache:
        raise RuntimeError("没有可补笔的提取缓存，请先提取")
    w, h = cache["w"], cache["h"]
    mask = cache["mask"]
    ink = None
    bd = 28 * 28 + 1
    x0, y0 = int(round(img_x)), int(round(img_y))
    for dy in range(-28, 29):
        for dx in range(-28, 29):
            xx, yy = x0 + dx, y0 + dy
            if xx < 1 or yy < 1 or xx >= w - 1 or yy >= h - 1:
                continue
            if not mask[yy, xx]:
                continue
            d = dx * dx + dy * dy
            if d < bd:
                bd = d
                ink = (xx, yy)
    if ink is None:
        raise RuntimeError("请点在线稿墨水上")
    visited = np.zeros((h, w), dtype=np.uint8)
    for c in cache.get("raw") or []:
        for i in range(0, len(c), 2):
            y, x = int(round(c[i][0])), int(round(c[i][1]))
            if 0 <= y < h and 0 <= x < w:
                visited[y, x] = 1
    path = trace_orientation_field(
        cache["brightness"], mask, cache["dir_x"], cache["dir_y"], cache["coherence"],
        ink[0], ink[1], cache["params"].invert_mask, cache["line_drawing"],
        visited, cache["tube_r"], cache["visit_hits"],
    )
    if not path or len(path) < 24:
        raise RuntimeError("这一笔太短，换一个更靠近线中心的点")
    raw = sanitize_line_art([path])
    raw = raw[0] if raw else path
    existing = cache.get("raw") or []
    for c in existing:
        if _mean_nearest(raw, c, 6) < 10:
            raise RuntimeError("这一笔已经有了，点另一条线")
    cache["raw"] = existing + [raw]
    p = cache["params"]
    n_samp = min(max(p.num_samples, 160), 480 if cache["line_drawing"] else 600)
    eps = max(2.8, min(p.rdp_epsilon, 7)) if cache["line_drawing"] else max(5, p.rdp_epsilon)
    traces = deduplicate_curves(cache["raw"], cache["brightness"], w, h, 10)
    smoothed = [fit_smooth(c, n_samp, eps, cache["line_drawing"]) for c in traces]
    smoothed = [c for c in smoothed if c and len(c) >= 2]
    axis = growth_axis_cfg(p, w, h)
    levels, colors = classify_curves(smoothed, cache["rgb"])
    profiles = estimate_depths(smoothed, cache["brightness"], w, h, axis["horizontal"], p.invert_mask)
    worlds = curves_to_world(smoothed, profiles, w, h)
    result.curves = []
    for i, pts in enumerate(smoothed):
        result.curves.append(
            ExtractedCurve(
                key="curve_%02d" % (i + 1),
                name="Curve %02d" % (i + 1),
                points_yx=np.asarray(pts, dtype=np.float64),
                points3d=worlds[i],
                level=levels[i] if i < len(levels) else 1,
                color_rgb=colors[i] if i < len(colors) else (255, 215, 0),
            )
        )
    return result


def extract_from_path(
    path: str,
    params: Optional[ExtractParams] = None,
    card: Optional[CardParams] = None,
    side_path: Optional[str] = None,
    top_path: Optional[str] = None,
    **kwargs,
) -> ExtractResult:
    side = load_rgb_u8(side_path) if side_path else None
    top = load_rgb_u8(top_path) if top_path else None
    return extract_from_rgb(load_rgb_u8(path), params, card, side, top, **kwargs)


def result_from_json(data: Dict[str, Any]) -> ExtractResult:
    card_d = data.get("card") or {}
    card = CardParams(
        count=int(card_d.get("count", 2)),
        width=float(card_d.get("width", 24)),
        taper=float(card_d.get("taper", 0.15)),
        cross_angle=float(card_d.get("crossAngle", card_d.get("cross_angle", 90))),
    )
    res = ExtractResult(
        version=str(data.get("dcc_version") or data.get("version") or VERSION),
        img_w=int(data.get("imgW") or 0),
        img_h=int(data.get("imgH") or 0),
        line_drawing=bool(data.get("lineDrawing")),
        card=card,
    )
    for i, entry in enumerate(data.get("curves") or []):
        if entry.get("points3d"):
            world = np.asarray(entry["points3d"], dtype=np.float64)
        elif entry.get("points3d_yup"):
            yup = np.asarray(entry["points3d_yup"], dtype=np.float64)
            world = np.stack([yup[:, 0], -yup[:, 1], yup[:, 2]], axis=1)
        else:
            raw = np.asarray(entry.get("points") or [], dtype=np.float64)
            if raw.size == 0:
                continue
            world = np.stack(
                [raw[:, 0] - res.img_w / 2, raw[:, 1] - res.img_h / 2, np.zeros(len(raw))],
                axis=1,
            )
        yx = np.stack(
            [world[:, 1] + res.img_h / 2, world[:, 0] + res.img_w / 2], axis=1
        ) if res.img_w and res.img_h else world[:, :2]
        col = entry.get("color") or [255, 215, 0]
        res.curves.append(
            ExtractedCurve(
                key=str(entry.get("key") or "curve_%02d" % (i + 1)),
                name=str(entry.get("name") or "Curve %02d" % (i + 1)),
                points_yx=yx,
                points3d=world,
                level=int(entry.get("level") or 1),
                color_rgb=(int(col[0]), int(col[1]), int(col[2])),
            )
        )
    return res


def load_json_file(path: str) -> ExtractResult:
    with open(path, "r", encoding="utf-8") as f:
        return result_from_json(json.load(f))


def save_json_file(result: ExtractResult, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result.to_json_dict(), f, ensure_ascii=False, indent=2)


def frames_along(points: np.ndarray):
    n = len(points)
    T = np.zeros((n, 3), dtype=np.float64)
    for i in range(n):
        a = points[max(0, i - 1)]
        b = points[min(n - 1, i + 1)]
        t = b - a
        L = np.linalg.norm(t)
        T[i] = (0, 0, 1) if L < 1e-8 else t / L
    n0 = np.cross(T[0], np.array([0.0, 0.0, 1.0]))
    if np.linalg.norm(n0) < 1e-4:
        n0 = np.cross(T[0], np.array([1.0, 0.0, 0.0]))
    n0 = n0 / (np.linalg.norm(n0) or 1.0)
    N = [n0]
    for i in range(1, n):
        prev = N[i - 1]
        d = float(np.dot(prev, T[i]))
        ni = prev - T[i] * d
        if np.linalg.norm(ni) < 1e-6:
            axis = np.cross(T[i - 1], T[i])
            if np.linalg.norm(axis) < 1e-6:
                ni = prev
            else:
                axis = axis / np.linalg.norm(axis)
                ni = np.cross(axis, T[i])
                ni = ni / (np.linalg.norm(ni) or 1.0)
        else:
            ni = ni / np.linalg.norm(ni)
        N.append(ni)
    N = np.asarray(N)
    B = np.cross(T, N)
    bn = np.linalg.norm(B, axis=1, keepdims=True)
    bn = np.where(bn < 1e-8, 1.0, bn)
    B = B / bn
    return T, N, B


def build_card_sheets(points: np.ndarray, card: CardParams, scale: float = 0.01):
    """Return list of (verts, faces, uvs) in the same space as scaled points."""
    n = len(points)
    if n < 2:
        return []
    _, nrm, binorm = frames_along(points)
    cross_rad = math.radians(card.cross_angle)
    count = max(1, int(card.count))
    sheets = []
    for k in range(count):
        if count == 1:
            angle = 0.0
        elif count == 2:
            angle = -cross_rad / 2 + k * cross_rad
        else:
            angle = k * math.pi / count
        ca, sa = math.cos(angle), math.sin(angle)
        verts = []
        uvs = []
        for i, p in enumerate(points):
            t = i / max(1, n - 1)
            dx = nrm[i] * ca + binorm[i] * sa
            half = card.width * (1.0 - card.taper * t) * scale
            left = p * scale - dx * half
            right = p * scale + dx * half
            verts.extend([left.tolist(), right.tolist()])
            uvs.extend([(0.0, t), (1.0, t)])
        faces = []
        for i in range(n - 1):
            a, b, c, d = i * 2, i * 2 + 1, (i + 1) * 2, (i + 1) * 2 + 1
            faces.append((a, b, d, c))
        sheets.append((verts, faces, uvs))
    return sheets


# ---------------------------------------------------------------------------
# Tri-view (same as app.html processTriViews / reconstructTriView / rectify)
# ---------------------------------------------------------------------------

def _ink_bbox(rgb: np.ndarray, thresh: int = 28):
    mx = rgb.max(axis=2)
    ys, xs = np.nonzero(mx > thresh)
    h, w = rgb.shape[:2]
    if len(xs) == 0:
        return {"x": 0, "y": 0, "w": w, "h": h, "empty": True}
    return {
        "x": int(xs.min()), "y": int(ys.min()),
        "w": int(xs.max() - xs.min() + 1), "h": int(ys.max() - ys.min() + 1),
        "empty": False,
    }


def _warp_ink_to_box(src: np.ndarray, src_box, dw, dh, dst_box) -> np.ndarray:
    out = np.zeros((dh, dw, 3), dtype=np.uint8)
    if src is None or src_box.get("empty") or dst_box["w"] < 1 or dst_box["h"] < 1:
        return out
    sx0, sy0 = src_box["x"], src_box["y"]
    swb, shb = max(1, src_box["w"]), max(1, src_box["h"])
    dx0, dy0 = dst_box["x"], dst_box["y"]
    dwb, dhb = max(1, dst_box["w"]), max(1, dst_box["h"])
    sh, sw = src.shape[:2]
    for y in range(sy0, min(sh, sy0 + shb)):
        for x in range(sx0, min(sw, sx0 + swb)):
            r, g, b = [int(v) for v in src[y, x]]
            if max(r, g, b) < 20:
                continue
            u = (x - sx0 + 0.5) / swb
            v = (y - sy0 + 0.5) / shb
            dx = int(round(dx0 + u * dwb))
            dy = int(round(dy0 + v * dhb))
            for px, py in ((dx, dy), (dx + 1, dy), (dx, dy + 1)):
                if 0 <= px < dw and 0 <= py < dh:
                    out[py, px] = (r, g, b)
    return out


def rectify_tri_views(front: np.ndarray, side: Optional[np.ndarray], top: Optional[np.ndarray]):
    if front is None or (side is None and top is None):
        return front, side, top
    H, W = front.shape[:2]
    fbox = _ink_bbox(front)
    if fbox["empty"]:
        return front, side, top
    z0, z1 = 0.14, 0.86
    side_dst = {
        "x": int(round(z0 * W)),
        "y": max(0, fbox["y"]),
        "w": max(8, int(round((z1 - z0) * W))),
        "h": max(8, min(H, fbox["y"] + fbox["h"]) - max(0, fbox["y"])),
    }
    top_dst = {
        "x": max(0, fbox["x"]),
        "y": int(round(z0 * H)),
        "w": max(8, min(W, fbox["x"] + fbox["w"]) - max(0, fbox["x"])),
        "h": max(8, int(round((z1 - z0) * H))),
    }
    if side is not None:
        side = _warp_ink_to_box(side, _ink_bbox(side), W, H, side_dst)
    if top is not None:
        top = _warp_ink_to_box(top, _ink_bbox(top), W, H, top_dst)
    return front, side, top


def _build_row_table(mask: np.ndarray):
    h, w = mask.shape
    rows = []
    for y in range(h):
        xs = np.nonzero(mask[y])[0]
        rows.append((xs / max(1, w - 1)).tolist() if len(xs) else [])
    return {"rows": rows, "w": w, "h": h}


def _build_col_table(mask: np.ndarray):
    h, w = mask.shape
    cols = []
    for x in range(w):
        ys = np.nonzero(mask[:, x])[0]
        cols.append((ys / max(1, h - 1)).tolist() if len(ys) else [])
    return {"cols": cols, "w": w, "h": h}


def _query_row_table(table, y_n, x_n):
    if not table:
        return None
    y = int(round(y_n * (table["h"] - 1)))
    for r in range(8):
        for yy in (y - r, y + r):
            if 0 <= yy < table["h"] and table["rows"][yy]:
                arr = table["rows"][yy]
                idx = max(0, min(len(arr) - 1, int(round(x_n * (len(arr) - 1)))))
                return arr[idx]
    return None


def _cluster_vals(arr, eps):
    if not arr:
        return []
    s = sorted(arr)
    out, sm, n = [], s[0], 1
    for i in range(1, len(s)):
        if s[i] - s[i - 1] <= eps:
            sm += s[i]
            n += 1
        else:
            out.append(sm / n)
            sm, n = s[i], 1
    out.append(sm / n)
    return out


def _z_cands_at_y(table, y_n, win):
    if not table:
        return []
    y = int(round(y_n * (table["h"] - 1)))
    c = []
    for d in range(-win, win + 1):
        yy = y + d
        if 0 <= yy < table["h"]:
            c.extend(table["rows"][yy])
    return _cluster_vals(c, 12 / max(1, table["w"] - 1))


def _z_cands_at_x(col_table, x_n, win):
    if not col_table:
        return []
    x = int(round(x_n * (col_table["w"] - 1)))
    c = []
    for d in range(-win, win + 1):
        xx = x + d
        if 0 <= xx < col_table["w"]:
            c.extend(col_table["cols"][xx])
    return _cluster_vals(c, 12 / max(1, col_table["h"] - 1))


def _smooth1d(arr, radius):
    n = len(arr)
    out = np.zeros(n, dtype=np.float64)
    for i in range(n):
        s = c = 0.0
        for k in range(-radius, radius + 1):
            j = i + k
            if 0 <= j < n and math.isfinite(arr[j]):
                s += arr[j]
                c += 1
        out[i] = s / c if c else arr[i]
    return out


def _mask_from_view(rgb: np.ndarray, p: ExtractParams, line_drawing: bool):
    inv = detect_invert_mask(rgb)
    m, _b = extract_mask(rgb, ExtractParams(**{**asdict(p), "invert_mask": inv, "auto_invert": False}), line_drawing)
    return m


def extract_line_curves_from_rgb(rgb: np.ndarray, p: Optional[ExtractParams] = None):
    """HTML extractLineCurvesFromRgb — side/top line-art OF (0.05 / 16 / 40)."""
    p = p or ExtractParams()
    rgb = rgb[..., :3]
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    h, w = rgb.shape[:2]
    mx = rgb.max(axis=2).astype(np.float64) / 255.0
    thr = min(p.bright_thresh, 0.22)
    mask = (mx >= thr).astype(np.uint8)
    solid = _close(mask, min(2, p.close_radius)) if p.close_radius > 0 else mask.copy()
    solid = _remove_small(solid, p.min_object_size)
    lp = ExtractParams(**{**asdict(p), "invert_mask": False, "min_length": 40})
    traces, _cache = _of_trace_all(
        rgb, mask, mx, lp, True, w, h,
        of_max_curves=16, of_min_bright=0.05, of_min_len=40,
    )
    return {"curves": traces, "w": w, "h": h, "mask": mask, "solid": solid}


def _stamp_polyline_mask(curves, w, h, radius: int = 1) -> np.ndarray:
    m = np.zeros((h, w), dtype=np.uint8)
    r = max(0, int(radius))
    for c in curves or []:
        for p in c:
            y, x = int(round(p[0])), int(round(p[1]))
            y0, y1 = max(0, y - r), min(h, y + r + 1)
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            m[y0:y1, x0:x1] = 1
    return m


def _curve_y_span(pts, h):
    ys = [p[0] / max(1, h - 1) for p in pts]
    ymin, ymax = min(ys), max(ys)
    return ymin, ymax, max(1e-6, ymax - ymin)


def _curve_x_span(pts, w):
    xs = [p[1] / max(1, w - 1) for p in pts]
    xmin, xmax = min(xs), max(xs)
    return xmin, xmax, max(1e-6, xmax - xmin)


def _match_front_to_side(front_curves, pack, front_w, front_h):
    if not pack or not pack.get("curves") or not front_curves:
        return [None] * len(front_curves or [])
    used = [False] * len(pack["curves"])
    match = [None] * len(front_curves)
    order = sorted(range(len(front_curves)), key=lambda i: -len(front_curves[i]))
    for fi in order:
        pts = front_curves[fi]
        fy0, fy1, fspan = _curve_y_span(pts, front_h)
        fx0, fx1, fxspan = _curve_x_span(pts, front_w)
        f_vert = fspan >= fxspan * 0.95
        best, best_score, best_rev = -1, 0.08, False
        for si, sc in enumerate(pack["curves"]):
            if used[si]:
                continue
            sy0, sy1, sspan = _curve_y_span(sc, pack["h"])
            sx0, sx1, sxspan = _curve_x_span(sc, pack["w"])
            s_vert = sspan >= sxspan * 0.95
            ov = max(0.0, min(fy1, sy1) - max(fy0, sy0))
            score = (ov / max(fspan, sspan)) * (0.5 + 0.5 * min(len(pts), len(sc)) / max(len(pts), len(sc)))
            score *= 1.7 if f_vert == s_vert else 0.4
            if score <= best_score:
                continue
            y0 = pts[0][0] / front_h
            y1 = pts[-1][0] / front_h
            s0 = sc[0][0] / pack["h"]
            s1 = sc[-1][0] / pack["h"]
            best, best_score = si, score
            best_rev = (abs(y0 - s1) + abs(y1 - s0)) < (abs(y0 - s0) + abs(y1 - s1))
        if best < 0:
            continue
        used[best] = True
        match[fi] = {"sideIdx": best, "reversed": best_rev}
    return match


def _match_front_to_top(front_curves, pack, front_w, front_h):
    if not pack or not pack.get("curves") or not front_curves:
        return [None] * len(front_curves or [])
    used = [False] * len(pack["curves"])
    match = [None] * len(front_curves)
    order = sorted(range(len(front_curves)), key=lambda i: -len(front_curves[i]))
    for fi in order:
        pts = front_curves[fi]
        fx0, fx1, fxspan = _curve_x_span(pts, front_w)
        fy0, fy1, fyspan = _curve_y_span(pts, front_h)
        f_horiz = fxspan >= fyspan * 0.95
        best, best_score, best_rev = -1, 0.08, False
        for ti, tc in enumerate(pack["curves"]):
            if used[ti]:
                continue
            tx0, tx1, txspan = _curve_x_span(tc, pack["w"])
            tz0, tz1, tzspan = _curve_y_span(tc, pack["h"])
            t_horiz = txspan >= tzspan * 0.95
            ov = max(0.0, min(fx1, tx1) - max(fx0, tx0))
            score = (ov / max(fxspan, txspan)) * (0.5 + 0.5 * min(len(pts), len(tc)) / max(len(pts), len(tc)))
            score *= 1.7 if f_horiz == t_horiz else 0.4
            if score <= best_score:
                continue
            x0 = pts[0][1] / front_w
            x1 = pts[-1][1] / front_w
            t0 = tc[0][1] / pack["w"]
            t1 = tc[-1][1] / pack["w"]
            best, best_score = ti, score
            best_rev = (abs(x0 - t1) + abs(x1 - t0)) < (abs(x0 - t0) + abs(x1 - t1))
        if best < 0:
            continue
        used[best] = True
        match[fi] = {"topIdx": best, "reversed": best_rev}
    return match


def _mask_axis_span(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    if len(xs) == 0:
        return {"yminN": 0.0, "ymaxN": 1.0, "xminN": 0.0, "xmaxN": 1.0}
    return {
        "yminN": float(ys.min()) / max(1, h - 1),
        "ymaxN": float(ys.max()) / max(1, h - 1),
        "xminN": float(xs.min()) / max(1, w - 1),
        "xmaxN": float(xs.max()) / max(1, w - 1),
    }


def _table_ink_span_rows(table):
    if not table:
        return {"xminN": 0.0, "xmaxN": 1.0, "yminN": 0.0, "ymaxN": 1.0}
    ymin, ymax = table["h"], -1
    xminN, xmaxN = 1.0, 0.0
    for y, row in enumerate(table["rows"]):
        if not row:
            continue
        if y < ymin:
            ymin = y
        if y > ymax:
            ymax = y
        xminN = min(xminN, min(row))
        xmaxN = max(xmaxN, max(row))
    if ymax < 0:
        return {"xminN": 0.0, "xmaxN": 1.0, "yminN": 0.0, "ymaxN": 1.0}
    return {
        "xminN": xminN, "xmaxN": xmaxN,
        "yminN": ymin / max(1, table["h"] - 1),
        "ymaxN": ymax / max(1, table["h"] - 1),
    }


def _table_ink_span_cols(table):
    if not table:
        return {"xminN": 0.0, "xmaxN": 1.0, "yminN": 0.0, "ymaxN": 1.0}
    xmin, xmax = table["w"], -1
    yminN, ymaxN = 1.0, 0.0
    for x, col in enumerate(table["cols"]):
        if not col:
            continue
        if x < xmin:
            xmin = x
        if x > xmax:
            xmax = x
        yminN = min(yminN, min(col))
        ymaxN = max(ymaxN, max(col))
    if xmax < 0:
        return {"xminN": 0.0, "xmaxN": 1.0, "yminN": 0.0, "ymaxN": 1.0}
    return {
        "xminN": xmin / max(1, table["w"] - 1),
        "xmaxN": xmax / max(1, table["w"] - 1),
        "yminN": yminN, "ymaxN": ymaxN,
    }


def _map_norm(v, a0, a1, b0, b1):
    t = (v - a0) / max(1e-6, a1 - a0)
    return b0 + max(0.0, min(1.0, t)) * (b1 - b0)


def _compute_tri_align(front_mask, side_tbl, top_cols):
    front = _mask_axis_span(front_mask) if front_mask is not None else {
        "yminN": 0.0, "ymaxN": 1.0, "xminN": 0.0, "xmaxN": 1.0
    }
    side = _table_ink_span_rows(side_tbl)
    top = _table_ink_span_cols(top_cols)
    return {"front": front, "side": side, "top": top}


def _detect_top_z_flip(front_mask, side_tbl, top_cols, align):
    if front_mask is None or not side_tbl or not top_cols:
        return False
    h, w = front_mask.shape
    step = max(4, int(round(min(w, h) / 80)))
    same = flip = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if not front_mask[y, x]:
                continue
            y_n = _map_norm(y / max(1, h - 1), align["front"]["yminN"], align["front"]["ymaxN"],
                            align["side"]["yminN"], align["side"]["ymaxN"])
            x_n = _map_norm(x / max(1, w - 1), align["front"]["xminN"], align["front"]["xmaxN"],
                            align["top"]["xminN"], align["top"]["xmaxN"])
            side_c = _z_cands_at_y(side_tbl, y_n, 3)
            top_c = _z_cands_at_x(top_cols, x_n, 3)
            if not side_c or not top_c:
                continue
            s = side_c[len(side_c) // 2]
            d0 = min(abs(s - t) for t in top_c)
            d1 = min(abs(s - (1 - t)) for t in top_c)
            if d1 < d0:
                flip += 1
            else:
                same += 1
    return flip > same + 4


def _interp_x_at_y(pts, y_pix, fallback):
    xs = []
    for i in range(1, len(pts)):
        y0, y1 = pts[i - 1][0], pts[i][0]
        if y_pix < min(y0, y1) - 2 or y_pix > max(y0, y1) + 2:
            continue
        if abs(y1 - y0) < 1e-6:
            xs.append((pts[i - 1][1] + pts[i][1]) / 2)
        else:
            a = (y_pix - y0) / (y1 - y0)
            if -0.2 <= a <= 1.2:
                xs.append(pts[i - 1][1] + a * (pts[i][1] - pts[i - 1][1]))
    if xs:
        return xs
    best, bx = 1e9, pts[0][1]
    for p in pts:
        d = abs(p[0] - y_pix)
        if d < best:
            best, bx = d, p[1]
    return [bx] if best < fallback else []


def _pick_z_from_list(vals, prev, scale):
    if not vals:
        return None
    if prev is None:
        return vals[0] / scale
    z, bd = vals[0] / scale, 1e9
    for v in vals:
        zn = v / scale
        d = abs(zn - prev)
        if d < bd:
            bd, z = d, zn
    return z


def _matched_side_curve(tri, idx, front_pts):
    pack = tri.get("side_pack")
    match = tri.get("side_match")
    if pack and match and idx is not None and idx < len(match) and match[idx]:
        c = pack["curves"][match[idx]["sideIdx"]]
        return list(reversed(c)) if match[idx]["reversed"] else c
    if not pack or not pack.get("curves") or front_pts is None:
        return None
    fw, fh = tri.get("front_w") or pack["w"], tri.get("front_h") or pack["h"]
    fy0, fy1, fspan = _curve_y_span(front_pts, fh)
    fx0, fx1, fxspan = _curve_x_span(front_pts, fw)
    f_vert = fspan >= fxspan * 0.95
    best, best_s = None, -1.0
    for c in pack["curves"]:
        sy0, sy1, sspan = _curve_y_span(c, pack["h"])
        sx0, sx1, sxspan = _curve_x_span(c, pack["w"])
        s_vert = sspan >= sxspan * 0.95
        ov = max(0.0, min(fy1, sy1) - max(fy0, sy0))
        score = ov * (0.3 + min(sspan, fspan))
        if f_vert == s_vert:
            score *= 1.6
        if score > best_s:
            best_s, best = score, c
    return best


def _lookup_side_zn(front_pts, i, idx, prev, tri, img_h):
    pack = tri.get("side_pack")
    align = tri.get("align")
    y_n = front_pts[i][0] / img_h
    if tri.get("align_ink") and align:
        y_n = _map_norm(y_n, align["front"]["yminN"], align["front"]["ymaxN"],
                        align["side"]["yminN"], align["side"]["ymaxN"])
    side = _matched_side_curve(tri, idx, front_pts)
    if pack and side:
        fb = max(28, pack["h"] * 0.04)
        z = _pick_z_from_list(_interp_x_at_y(side, y_n * (pack["h"] - 1), fb), prev, max(1, pack["w"] - 1))
        if z is not None:
            return z
    cands = _z_cands_at_y(tri.get("side"), y_n, 6)
    if not cands:
        return None
    z, bd = cands[0], 1e9
    for cand in cands:
        d = abs(cand - 0.5) if prev is None else abs(cand - prev)
        if d < bd:
            bd, z = d, cand
    return z


def build_tri_state(front_rgb, front_mask, side_rgb, top_rgb, p: ExtractParams,
                    line_drawing: bool, front_curves=None):
    side_tbl = _build_row_table(_mask_from_view(side_rgb, p, line_drawing)) if side_rgb is not None else None
    top_tbl = _build_row_table(_mask_from_view(top_rgb, p, line_drawing)) if top_rgb is not None else None
    top_cols = None
    side_pack = top_pack = None
    if line_drawing and side_rgb is not None:
        side_pack = extract_line_curves_from_rgb(side_rgb, p)
    if line_drawing and top_rgb is not None:
        top_pack = extract_line_curves_from_rgb(top_rgb, p)
        ink = _stamp_polyline_mask(top_pack["curves"], top_pack["w"], top_pack["h"], 1)
        top_cols = _build_col_table(ink)
        top_tbl = _build_row_table(ink)
    elif top_rgb is not None:
        tm = _mask_from_view(top_rgb, p, line_drawing)
        top_cols = _build_col_table(tm)
    align = _compute_tri_align(front_mask, side_tbl, top_cols)
    top_flip = _detect_top_z_flip(front_mask, side_tbl, top_cols, align) if line_drawing else False
    fh, fw = (front_mask.shape[:2] if front_mask is not None else (0, 0))
    side_match = _match_front_to_side(front_curves, side_pack, fw, fh) if line_drawing else None
    top_match = _match_front_to_top(front_curves, top_pack, fw, fh) if line_drawing else None
    return {
        "side": side_tbl, "top": top_tbl, "top_cols": top_cols, "line": line_drawing,
        "side_pack": side_pack, "top_pack": top_pack,
        "side_match": side_match, "top_match": top_match,
        "align": align, "align_ink": bool(line_drawing and p.tri_align_ink),
        "top_flip": top_flip, "front_w": fw, "front_h": fh,
    }


def reconstruct_tri_z(front_pts, img_w, img_h, tri, trust_top: float, idx=None):
    n = len(front_pts)
    w_top = max(0.0, min(1.0, trust_top))
    z_n = np.zeros(n, dtype=np.float64)
    prev = None
    align = tri.get("align")
    align_on = bool(tri.get("align_ink") and align)
    flip = bool(tri.get("top_flip"))
    for i, pt in enumerate(front_pts):
        y_n = pt[0] / img_h
        x_n = pt[1] / img_w
        if align_on:
            y_n = _map_norm(y_n, align["front"]["yminN"], align["front"]["ymaxN"],
                            align["side"]["yminN"], align["side"]["ymaxN"])
            x_n = _map_norm(x_n, align["front"]["xminN"], align["front"]["xmaxN"],
                            align["top"]["xminN"], align["top"]["xmaxN"])
        side_c = _z_cands_at_y(tri.get("side"), y_n, 4)
        z_side = None
        if side_c:
            z_side = side_c[0]
            bd = 1e9
            for cand in side_c:
                d = abs(cand - 0.5) if prev is None else abs(cand - prev)
                if d < bd:
                    bd, z_side = d, cand
        else:
            z_side = _lookup_side_zn(front_pts, i, idx, prev, tri, img_h)
        top_c = _z_cands_at_x(tri.get("top_cols") or None, x_n, 4)
        z_top = None
        if top_c:
            z_top = (1 - top_c[0]) if flip else top_c[0]
            bd = 1e9
            for cand in top_c:
                cz = (1 - cand) if flip else cand
                d = abs(cz - 0.5) if prev is None else abs(cz - prev)
                if d < bd:
                    bd, z_top = d, cz
        if z_side is None and z_top is None:
            z = prev if prev is not None else 0.5
        elif z_side is None:
            z = z_top
        elif z_top is None:
            z = z_side
        else:
            z = z_side * (1 - w_top) + z_top * w_top
        if prev is not None:
            dy = abs(front_pts[i][0] - front_pts[max(0, i - 1)][0]) / max(1, img_h)
            max_step = 0.04 + dy * 3
            if abs(z - prev) > max_step:
                z = prev + math.copysign(max_step, z - prev)
        z_n[i] = z
        prev = z
    rad = max(14, int(round(n / 22)))
    zs = _smooth1d(_smooth1d(z_n, rad), rad)
    return zs


def front_to_world_tri(curve, idx, w, h, tri, trust_top, line_drawing):
    depth_range = w * 0.35
    if line_drawing:
        z_n = reconstruct_tri_z(curve, w, h, tri, trust_top, idx=idx)
        zs = (z_n - 0.5) * 2 * depth_range
    else:
        zs = []
        for p in curve:
            z_side = _query_row_table(tri.get("side"), p[0] / h, p[1] / w)
            z_n = z_side if z_side is not None else p[1] / w
            zs.append((z_n - 0.5) * 2 * depth_range)
        zs = _smooth1d(zs, 6)
    pts = []
    for i, p in enumerate(curve):
        pts.append([p[1] - w / 2, p[0] - h / 2, float(zs[i])])
    return np.asarray(pts, dtype=np.float64)


def extract_from_rgb(
    rgb: np.ndarray,
    params: Optional[ExtractParams] = None,
    card: Optional[CardParams] = None,
    side_rgb: Optional[np.ndarray] = None,
    top_rgb: Optional[np.ndarray] = None,
    trust_top: Optional[float] = None,
    tri_rectify: Optional[bool] = None,
) -> ExtractResult:
    result = _extract_from_rgb_single(rgb, params, card)
    p = params or ExtractParams()
    if side_rgb is None and top_rgb is None:
        return result
    tt = p.trust_top if trust_top is None else trust_top
    do_rect = p.tri_rectify if tri_rectify is None else tri_rectify
    front = rgb[..., :3]
    if front.dtype != np.uint8:
        front = (np.clip(front, 0, 255)).astype(np.uint8)
    if do_rect:
        front, side_rgb, top_rgb = rectify_tri_views(front, side_rgb, top_rgb)
        if side_rgb is not None or top_rgb is not None:
            result = _extract_from_rgb_single(front, params, card)
    cache = result.of_cache or {}
    mask = cache.get("mask")
    if mask is None:
        return result
    tri = build_tri_state(
        front, mask, side_rgb, top_rgb, p, result.line_drawing,
        front_curves=[c.points_yx for c in result.curves],
    )
    worlds = [
        front_to_world_tri(c.points_yx, i, result.img_w, result.img_h, tri, tt, result.line_drawing)
        for i, c in enumerate(result.curves)
    ]
    for i, c in enumerate(result.curves):
        c.points3d = worlds[i]
    cache["tri"] = tri
    result.of_cache = cache
    return result


def _format_fbx_num(v: float) -> str:
    return ("%.6f" % float(v)).rstrip("0").rstrip(".") if abs(v) > 1e-12 else "0"


def export_card_fbx(result: ExtractResult, path: str, scale: float = 0.01) -> None:
    """ASCII FBX, Y-up, same convention as the HTML 面片 FBX."""
    V, UV, PVI, NRM = [], [], [], []
    for entry in result.curves:
        for verts, faces, uvs in build_card_sheets(entry.points3d, result.card, scale=scale):
            base = len(V) // 3
            for i, (x, y, z) in enumerate(verts):
                V.extend([x, -y, z])
                UV.extend([uvs[i][0], uvs[i][1]])
            for a, b, d, c in faces:
                tris = ((a, b, c), (b, d, c))
                for i0, i1, i2 in tris:
                    ia, ib, ic = base + i0, base + i1, base + i2
                    ax, ay, az = V[ia * 3], V[ia * 3 + 1], V[ia * 3 + 2]
                    ux, uy, uz = V[ib * 3] - ax, V[ib * 3 + 1] - ay, V[ib * 3 + 2] - az
                    vx, vy, vz = V[ic * 3] - ax, V[ic * 3 + 1] - ay, V[ic * 3 + 2] - az
                    nx = uy * vz - uz * vy
                    ny = uz * vx - ux * vz
                    nz = ux * vy - uy * vx
                    nl = math.hypot(nx, ny, nz) or 1.0
                    PVI.extend([ia, ib, -ic - 1])
                    for _ in range(3):
                        NRM.extend([nx / nl, ny / nl, nz / nl])

    def chunk(arr, per):
        s = ""
        for i, v in enumerate(arr):
            if i % per == 0:
                s += "\t\t\t"
            s += _format_fbx_num(v) if isinstance(v, float) else str(v)
            if i < len(arr) - 1:
                s += ","
            if i % per == per - 1 or i == len(arr) - 1:
                s += "\n"
        return s

    fbx = f"""; FBX 7.4.0 ASCII — Curve Extractor intersecting cards
FBXHeaderExtension:  {{
\tFBXHeaderVersion: 1003
\tFBXVersion: 7400
\tCreator: "Curve Extractor"
}}
GlobalSettings:  {{
\tVersion: 1000
\tProperties70:  {{
\t\tP: "UpAxis", "int", "Integer", "",1
\t\tP: "UpAxisSign", "int", "Integer", "",1
\t\tP: "FrontAxis", "int", "Integer", "",2
\t\tP: "FrontAxisSign", "int", "Integer", "",1
\t\tP: "CoordAxis", "int", "Integer", "",0
\t\tP: "CoordAxisSign", "int", "Integer", "",1
\t\tP: "UnitScaleFactor", "double", "Number", "",1
\t}}
}}
Definitions:  {{
\tVersion: 100
\tCount: 2
\tObjectType: "GlobalSettings" {{Count: 1}}
\tObjectType: "Model" {{Count: 1}}
\tObjectType: "Geometry" {{Count: 1}}
}}
Objects:  {{
\tGeometry: 100000, "Geometry::cards", "Mesh" {{
\t\tVertices: *{len(V)} {{
{chunk(V, 9)}\t\t}}
\t\tPolygonVertexIndex: *{len(PVI)} {{
{chunk(PVI, 12)}\t\t}}
\t\tGeometryVersion: 124
\t\tLayerElementNormal: 0 {{
\t\t\tVersion: 101
\t\t\tName: "Normals"
\t\t\tMappingInformationType: "ByPolygonVertex"
\t\t\tReferenceInformationType: "Direct"
\t\t\tNormals: *{len(NRM)} {{
{chunk(NRM, 9)}\t\t\t}}
\t\t}}
\t\tLayerElementUV: 0 {{
\t\t\tVersion: 101
\t\t\tName: "map1"
\t\t\tMappingInformationType: "ByPolygonVertex"
\t\t\tReferenceInformationType: "Direct"
\t\t\tUV: *{len(UV)} {{
{chunk(UV, 8)}\t\t\t}}
\t\t}}
\t}}
\tModel: 200000, "Model::CurveExtractorCards", "Mesh" {{
\t\tVersion: 232
\t}}
}}
Connections:  {{
\tC: "OO",100000,200000
}}
"""
    Path = __import__("pathlib").Path
    Path(path).write_text(fbx, encoding="utf-8")


_CURVE_SVG_COLORS = ("#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8")


def export_svg(result: ExtractResult, path: str) -> None:
    w, h = result.img_w or 1024, result.img_h or 1024
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h),
        '<rect width="100%" height="100%" fill="black"/>',
    ]
    for i, c in enumerate(result.curves):
        color = _CURVE_SVG_COLORS[i % len(_CURVE_SVG_COLORS)]
        d = "M " + " L ".join("%.1f %.1f" % (p[1], p[0]) for p in c.points_yx)
        parts.append(
            '<path d="%s" fill="none" stroke="%s" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" id="%s" name="%s"/>'
            % (d, color, c.key, c.name)
        )
    parts.append("</svg>")
    __import__("pathlib").Path(path).write_text("\n".join(parts), encoding="utf-8")


def export_dxf(result: ExtractResult, path: str) -> None:
    """HTML exportDXF: AC1009 POLYLINE + VERTEX."""
    lines = [
        "0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
        "0", "ENDSEC", "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER",
        "70", str(len(result.curves)),
    ]
    for i, c in enumerate(result.curves):
        lines += ["0", "LAYER", "2", c.key, "70", "0", "62", str((i + 1) % 256), "6", "CONTINUOUS"]
    lines += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
    for c in result.curves:
        pts = list(c.points_yx)
        if len(pts) < 2:
            continue
        lines += ["0", "POLYLINE", "8", c.key, "66", "1", "70", "0", "10", "0.0", "20", "0.0", "30", "0.0"]
        for p in pts:
            lines += ["0", "VERTEX", "8", c.key, "10", "%.3f" % p[1], "20", "%.3f" % (-p[0]), "30", "0.0"]
        lines += ["0", "SEQEND", "8", c.key]
    lines += ["0", "ENDSEC", "0", "EOF"]
    __import__("pathlib").Path(path).write_text("\n".join(lines), encoding="utf-8")


def export_obj_lines(result: ExtractResult, path: str) -> None:
    """HTML exportOBJ: 2D polylines as OBJ l, stacked in Z."""
    lines = ["# Curve Extractor OBJ export"]
    v_off = 1
    n = len(result.curves)
    for i, c in enumerate(result.curves):
        z = (i - n / 2) * 0.5
        pts = list(c.points_yx)
        for p in pts:
            lines.append("v %.3f %.3f %.3f" % (p[1], -p[0], z))
        for j in range(len(pts) - 1):
            lines.append("l %d %d" % (v_off + j, v_off + j + 1))
        v_off += len(pts)
    __import__("pathlib").Path(path).write_text("\n".join(lines), encoding="utf-8")


def export_obj_cards(result: ExtractResult, path: str, scale: float = 0.01) -> None:
    lines = ["# Curve Extractor cards"]
    v_base = 1
    for entry in result.curves:
        for verts, faces, uvs in build_card_sheets(entry.points3d, result.card, scale=scale):
            for x, y, z in verts:
                lines.append("v %.6f %.6f %.6f" % (x, -y, z))
            for u, v in uvs:
                lines.append("vt %.6f %.6f" % (u, v))
            for a, b, d, c in faces:
                def idx(i):
                    return "%d/%d" % (v_base + i, v_base + i)
                lines.append("f %s %s %s %s" % (idx(a), idx(b), idx(d), idx(c)))
            v_base += len(verts)
    __import__("pathlib").Path(path).write_text("\n".join(lines), encoding="utf-8")

