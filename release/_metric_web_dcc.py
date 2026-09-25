import base64
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(r"h:\tool\curve-extractor")
sys.path.insert(0, str(ROOT / "dcc_shared"))
import core  # noqa: E402

demo = ROOT / "release" / "preview" / "00_demo_source.png"
rgb = np.asarray(Image.open(demo))
dcc = core.extract_from_rgb(rgb)
data_url = "data:image/png;base64," + base64.b64encode(demo.read_bytes()).decode("ascii")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto((ROOT / "app.html").as_uri(), wait_until="domcontentloaded")
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
            extractAll();
            resolve(1);
          };
          img.onerror = () => reject('img');
          img.src = url;
        })""",
        data_url,
    )
    for _ in range(80):
        busy = page.evaluate("() => !!document.getElementById('btnExtract').disabled")
        status = page.evaluate("() => document.getElementById('status').textContent")
        if (not busy) and str(status).startswith("完成"):
            break
        time.sleep(0.2)
    web = page.evaluate("() => (S.smoothedCurves||[]).map(cd => (cd.smoothed||[]).map(p => [p[0], p[1]]))")
    browser.close()


def nn(a, b):
    A = np.asarray(a)
    B = np.asarray(b)
    acc = 0.0
    n = 0
    step = max(1, len(A) // 80)
    for i in range(0, len(A), step):
        acc += float(np.hypot(B[:, 0] - A[i, 0], B[:, 1] - A[i, 1]).min())
        n += 1
    return acc / max(1, n)


print("web", len(web), "dcc", len(dcc.curves))
used = set()
dists = []
for i, c in enumerate(dcc.curves):
    best, bj = 1e9, -1
    for j, w in enumerate(web):
        if j in used:
            continue
        d = min(nn(c.points_yx, w), nn(w, c.points_yx))
        if d < best:
            best, bj = d, j
    used.add(bj)
    dists.append(best)
    print("dcc%d <-> web%d  %.2f px" % (i + 1, bj + 1, best))
print("mean", float(np.mean(dists)))
