"""Web vs DCC on the production gold-glow plate."""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(r"h:\tool\curve-extractor")
OUT = ROOT / "release" / "preview"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "dcc_shared"))
import core  # noqa: E402

SRC = Path(
    r"C:\Users\54364\.cursor\projects\h-tool\assets"
    r"\c__Users_54364_AppData_Roaming_Cursor_User_workspaceStorage"
    r"_b0b4c352806c626f140155c845b61002_images"
    r"_b32a1ff60dc52e2c79c93e79e1fcf8a5-45c8ae98-7788-412d-ad87-6642f5c693e3.png"
)
PROD = OUT / "production_glow.png"


def _mean_nearest(a, b, step=8):
    if not a or not b:
        return 1e9
    aa = np.asarray(a[::step], dtype=np.float64)
    bb = np.asarray(b, dtype=np.float64)
    d = 0.0
    for p in aa:
        d += float(np.sqrt(((bb - p) ** 2).sum(axis=1).min()))
    return d / max(1, len(aa))


def overlay(rgb, curves, color, width=3):
    im = Image.fromarray(rgb).convert("RGB")
    dr = ImageDraw.Draw(im)
    for c in curves:
        pts = [(float(p[1]), float(p[0])) for p in c]
        if len(pts) >= 2:
            dr.line(pts, fill=color, width=width)
    return im


def run_web(path: Path):
    import base64
    from io import BytesIO

    from playwright.sync_api import sync_playwright

    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    data_url = "data:image/png;base64," + b64
    app = (ROOT / "app.html").as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto(app, wait_until="domcontentloaded")
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
                if (typeof drawCanvas === 'function') drawCanvas('canvasOriginal', S.rgb);
                extractAll();
                resolve(1);
              };
              img.onerror = () => reject('img');
              img.src = url;
            })""",
            data_url,
        )
        deadline = time.time() + 180
        status = ""
        while time.time() < deadline:
            busy = page.evaluate("() => !!document.getElementById('btnExtract').disabled")
            status = page.evaluate("() => document.getElementById('status').textContent")
            if (not busy) and str(status).startswith("完成"):
                break
            time.sleep(0.4)
        dump = page.evaluate(
            """() => ({
              status: document.getElementById('status').textContent,
              n: (S.smoothedCurves||[]).length,
              line: !!S.lineDrawing,
              axis: (typeof getGrowthAxis === 'function') ? getGrowthAxis() : null,
              curves: (S.smoothedCurves||[]).map(cd => (cd.smoothed||[]).map(p => [p[0], p[1]])),
            })"""
        )
        page.evaluate(
            """() => {
              if (typeof drawCurves === 'function' && S.smoothedCurves)
                drawCurves('canvasCurves', S.smoothedCurves, false, true);
            }"""
        )
        time.sleep(0.2)
        uri = page.evaluate(
            """() => { const c=document.getElementById('canvasCurves');
              if (!c || !c.width) return null;
              try { return c.toDataURL('image/png'); } catch(e) { return null; } }"""
        )
        web_canvas = None
        if uri and str(uri).startswith("data:image/png"):
            raw = base64.b64decode(uri.split(",", 1)[1])
            web_canvas = Image.open(BytesIO(raw)).convert("RGB")
        browser.close()
        return dump, web_canvas


def main():
    if not SRC.exists():
        raise SystemExit("missing production source: " + str(SRC))
    shutil.copy2(SRC, PROD)
    im = Image.open(PROD).convert("RGB")
    rgb = np.asarray(im)
    print("prod", rgb.shape)

    print("dcc...")
    t0 = time.time()
    result = core.extract_from_rgb(rgb)
    print("dcc n=", len(result.curves), "line", result.line_drawing, "ms", int((time.time() - t0) * 1000))

    web = None
    web_canvas = None
    try:
        print("web...")
        web, web_canvas = run_web(PROD)
        print("web", web["status"], "n=", web["n"], "line", web["line"], "axis", web.get("axis"))
    except Exception as e:
        print("web skip:", e)

    dcc_curves = [c.points_yx.tolist() for c in result.curves]
    dcc_ov = overlay(rgb, dcc_curves, (255, 210, 70), 3)
    dcc_ov.save(OUT / "prod_dcc_overlay.png")

    if web:
        web_ov = overlay(rgb, web["curves"], (80, 220, 255), 3)
        web_ov.save(OUT / "prod_web_overlay.png")
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
        both.save(OUT / "prod_overlay_both.png")
        pairs = []
        used = set()
        for i, wc in enumerate(web["curves"]):
            best, bd = -1, 1e9
            for j, dc in enumerate(dcc_curves):
                if j in used:
                    continue
                d = _mean_nearest(wc, dc)
                if d < bd:
                    bd, best = d, j
            if best >= 0:
                used.add(best)
                pairs.append(bd)
        mean_d = float(np.mean(pairs)) if pairs else 1e9
        print("paired", len(pairs), "mean_nearest_px", round(mean_d, 3), "pairs", [round(x, 3) for x in pairs])
        (OUT / "prod_metric.json").write_text(
            json.dumps(
                {
                    "web_n": web["n"],
                    "dcc_n": len(result.curves),
                    "web_line": web["line"],
                    "dcc_line": result.line_drawing,
                    "mean_nearest_px": mean_d,
                    "pairs": pairs,
                    "shape": list(rgb.shape),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if web_canvas:
            web_canvas.save(OUT / "prod_web_canvasCurves.png")

        def label(im, text):
            canvas = Image.new("RGB", (im.width, im.height + 32), (20, 20, 22))
            canvas.paste(im, (0, 32))
            ImageDraw.Draw(canvas).text((10, 8), text, fill=(230, 230, 230))
            return canvas

        sheet = Image.new("RGB", (both.width, both.height * 2 + 40), (16, 16, 18))
        a = label(web_ov, "网页 %d 根" % web["n"])
        b = label(dcc_ov, "插件核 %d 根" % len(result.curves))
        c = label(both, "叠：青=网页  黄=插件  mean=%.2fpx" % mean_d)
        # scale to fit
        w = min(1600, both.width)
        def rs(im):
            h = int(im.height * w / im.width)
            return im.resize((w, h))
        ra, rb, rc = rs(a), rs(b), rs(c)
        sheet = Image.new("RGB", (w, ra.height + rb.height + rc.height + 16), (16, 16, 18))
        y = 0
        for im in (ra, rb, rc):
            sheet.paste(im, (0, y))
            y += im.height + 8
        sheet.save(OUT / "compare_production_web_vs_dcc.png")
        print("wrote", OUT / "compare_production_web_vs_dcc.png")
    else:
        (OUT / "prod_metric.json").write_text(
            json.dumps({"dcc_n": len(result.curves), "dcc_line": result.line_drawing, "web": None}),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
