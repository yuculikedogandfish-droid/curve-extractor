"""Compare web extractAll vs DCC core on the built-in demo image."""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(r"h:\tool\curve-extractor")
APP = ROOT / "app.html"
OUT = ROOT / "release" / "preview"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "dcc_shared"))
import core  # noqa: E402


def make_demo_rgb():
    from PIL import ImageDraw as D

    w, h = 800, 500
    im = Image.new("RGB", (w, h), (0, 0, 0))
    dr = D.Draw(im)
    demo = [
        ((400, 450), (150, 100), (300, 350), (200, 200)),
        ((400, 450), (650, 100), (500, 350), (600, 200)),
        ((400, 450), (400, 50), (400, 350), (400, 200)),
        ((400, 450), (100, 350), (300, 420), (180, 380)),
        ((400, 450), (700, 350), (500, 420), (620, 380)),
    ]
    for start, end, c0, c1 in demo:
        for t in range(80):
            u = t / 79.0
            # cubic bezier
            p0, p1, p2, p3 = start, c0, c1, end
            x = (
                (1 - u) ** 3 * p0[0]
                + 3 * (1 - u) ** 2 * u * p1[0]
                + 3 * (1 - u) * u ** 2 * p2[0]
                + u ** 3 * p3[0]
            )
            y = (
                (1 - u) ** 3 * p0[1]
                + 3 * (1 - u) ** 2 * u * p1[1]
                + 3 * (1 - u) * u ** 2 * p2[1]
                + u ** 3 * p3[1]
            )
            r = int(255)
            g = int(215 * (1 - u) + 102 * u)
            b = int(0)
            dr.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(r, g, b))
    return im


def decode_data_url(uri: str) -> Image.Image:
    raw = base64.b64decode(uri.split(",", 1)[1])
    from io import BytesIO

    return Image.open(BytesIO(raw)).convert("RGB")


def overlay_curves(rgb: np.ndarray, curves, color=(255, 230, 80), width=3) -> Image.Image:
    im = Image.fromarray(rgb).convert("RGB")
    dr = ImageDraw.Draw(im)
    for c in curves:
        pts = [(float(p[1]), float(p[0])) for p in c]
        if len(pts) >= 2:
            dr.line(pts, fill=color, width=width)
    return im


def project_3d(pts, w, h, rot_y=0.55, rot_x=0.35, zoom=0.92):
    """Rough match to the HTML Canvas projection for a preview still."""
    out = []
    cy, sy = np.cos(rot_y), np.sin(rot_y)
    cx, sx = np.cos(rot_x), np.sin(rot_x)
    for x, y, z in pts:
        # y is image-down in html world
        X = x * cy + z * sy
        Z = -x * sy + z * cy
        Y = y * cx - Z * sx
        Z2 = y * sx + Z * cx
        f = 700 / (700 + Z2 * zoom)
        px = w * 0.5 + X * f * zoom
        py = h * 0.52 + Y * f * zoom
        out.append((px, py))
    return out


def draw_3d_preview(result: core.ExtractResult, w=800, h=500) -> Image.Image:
    im = Image.new("RGB", (w, h), (12, 12, 14))
    dr = ImageDraw.Draw(im)
    dr.ellipse((w * 0.5 - 90, h * 0.78, w * 0.5 + 90, h * 0.88), outline=(40, 40, 48))
    cols = [(255, 210, 70), (90, 200, 255), (255, 120, 90), (160, 230, 140), (220, 160, 255)]
    for i, c in enumerate(result.curves):
        pts = project_3d(c.points3d, w, h)
        if len(pts) >= 2:
            dr.line(pts, fill=cols[i % len(cols)], width=3)
    return im


def run_web(demo_path: Path):
    b64 = base64.b64encode(demo_path.read_bytes()).decode("ascii")
    data_url = "data:image/png;base64," + b64
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(APP.as_uri(), wait_until="domcontentloaded")
        page.wait_for_function("typeof extractAll === 'function'")
        page.evaluate(
            """(url) => new Promise((resolve, reject) => {
              const img = new Image();
              img.onload = () => {
                const cv = document.createElement('canvas');
                cv.width = img.width; cv.height = img.height;
                const cx = cv.getContext('2d');
                cx.drawImage(img, 0, 0);
                S.image = img; S.imgW = img.width; S.imgH = img.height;
                S.rgb = cx.getImageData(0, 0, img.width, img.height);
                S.inputMode = 'single'; S.traceMode = 'of';
                drawCanvas('canvasOriginal', S.rgb);
                extractAll();
                resolve(1);
              };
              img.onerror = () => reject('img');
              img.src = url;
            })""",
            data_url,
        )
        deadline = time.time() + 90
        status = ""
        while time.time() < deadline:
            busy = page.evaluate("() => !!document.getElementById('btnExtract').disabled")
            status = page.evaluate("() => document.getElementById('status').textContent")
            if (not busy) and str(status).startswith("完成"):
                break
            time.sleep(0.3)
        dump = page.evaluate(
            """() => ({
              status: document.getElementById('status').textContent,
              n: (S.smoothedCurves||[]).length,
              line: !!S.lineDrawing,
              curves: (S.smoothedCurves||[]).map(cd => (cd.smoothed||[]).map(p => [p[0], p[1]])),
              world: (S.smoothedCurves||[]).map((cd,i) =>
                buildCurveWorldPoints(cd,i).map(p => [p.x,p.y,p.z])),
            })"""
        )
        page.evaluate(
            """() => {
              const t = [...document.querySelectorAll('.view-tab')].find(x => x.dataset.view === '3d');
              document.querySelectorAll('.view-tab').forEach(x => x.classList.remove('active'));
              document.querySelectorAll('.view-pane').forEach(p => p.classList.remove('active'));
              if (t) t.classList.add('active');
              const pane = document.getElementById('pane-3d');
              if (pane) pane.classList.add('active');
              if (typeof draw3DView === 'function') draw3DView();
              if (typeof drawCurves === 'function' && S.smoothedCurves)
                drawCurves('canvasCurves', S.smoothedCurves, false, true);
            }"""
        )
        time.sleep(0.3)
        shots = {}
        for cid in ("canvasOriginal", "canvasMask", "canvasCurves", "canvas3d"):
            uri = page.evaluate(
                "(id) => { const c=document.getElementById(id); if (!c || !c.width) return null; try { return c.toDataURL('image/png'); } catch(e) { return null; } }",
                cid,
            )
            if uri and uri.startswith("data:image/png"):
                try:
                    shots[cid] = decode_data_url(uri)
                except Exception as e:
                    print("skip", cid, e)
        browser.close()
        return dump, shots


def label(im: Image.Image, text: str) -> Image.Image:
    canvas = Image.new("RGB", (im.width, im.height + 36), (20, 20, 22))
    canvas.paste(im, (0, 36))
    dr = ImageDraw.Draw(canvas)
    dr.text((12, 10), text, fill=(230, 230, 230))
    return canvas


def hstack(images):
    h = max(im.height for im in images)
    w = sum(im.width for im in images) + 8 * (len(images) - 1)
    out = Image.new("RGB", (w, h), (16, 16, 18))
    x = 0
    for im in images:
        out.paste(im, (x, 0))
        x += im.width + 8
    return out


def main():
    demo = make_demo_rgb()
    demo_path = OUT / "00_demo_source.png"
    demo.save(demo_path)
    rgb = np.asarray(demo)

    print("web extract...")
    web, shots = run_web(demo_path)
    print("web", web["status"], "n=", web["n"], "line", web["line"])
    (OUT / "web_curves.json").write_text(json.dumps({"n": web["n"], "status": web["status"]}), encoding="utf-8")

    print("dcc extract...")
    result = core.extract_from_rgb(rgb)
    print("dcc n=", len(result.curves), "line", result.line_drawing)

    web_overlay = overlay_curves(rgb, web["curves"], (80, 220, 255), 3)
    dcc_curves = [c.points_yx for c in result.curves]
    dcc_overlay = overlay_curves(rgb, dcc_curves, (255, 210, 70), 3)
    both = Image.fromarray(rgb).convert("RGB")
    dr = ImageDraw.Draw(both)
    for c in web["curves"]:
        pts = [(float(p[1]), float(p[0])) for p in c]
        if len(pts) >= 2:
            dr.line(pts, fill=(80, 220, 255), width=4)
    for c in dcc_curves:
        pts = [(float(p[1]), float(p[0])) for p in c]
        if len(pts) >= 2:
            dr.line(pts, fill=(255, 210, 70), width=2)

    dcc_3d = draw_3d_preview(result)
    web_3d = shots.get("canvas3d") or Image.new("RGB", (800, 500), (0, 0, 0))

    row1 = hstack(
        [
            label(demo, "1. 同一张示例图（网页加载示例）"),
            label(shots.get("canvasCurves") or web_overlay, "2. 网页 曲线页  %d根" % web["n"]),
            label(dcc_overlay, "3. 插件核 曲线叠加  %d根" % len(result.curves)),
        ]
    )
    row2 = hstack(
        [
            label(web_3d.resize((800, 500)), "4. 网页 3D 预览"),
            label(dcc_3d, "5. 插件核 3D 预览（同世界坐标投影）"),
            label(both, "6. 叠在一起：青=网页  黄=插件"),
        ]
    )
    sheet = Image.new("RGB", (row1.width, row1.height + row2.height + 8), (16, 16, 18))
    sheet.paste(row1, (0, 0))
    sheet.paste(row2, (0, row1.height + 8))
    sheet_path = OUT / "compare_demo_web_vs_dcc.png"
    sheet.save(sheet_path)

    demo.save(OUT / "01_source.png")
    web_overlay.save(OUT / "02_web_overlay.png")
    dcc_overlay.save(OUT / "03_dcc_overlay.png")
    both.save(OUT / "04_overlay_both.png")
    web_3d.save(OUT / "05_web_3d.png")
    dcc_3d.save(OUT / "06_dcc_3d.png")
    if "canvasCurves" in shots:
        shots["canvasCurves"].save(OUT / "02b_web_canvasCurves.png")
    print("wrote", sheet_path)


if __name__ == "__main__":
    main()
