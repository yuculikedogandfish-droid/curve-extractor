"""
三视图素材整理：统一尺寸、背景纯黑、去除坐标轴、标注正/侧/顶。
"""
import os, numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

RAW = r'H:\tool\curve-extractor\input\tri_labeled\raw'
OUT = r'H:\tool\curve-extractor\input\tri_labeled\processed'
os.makedirs(OUT, exist_ok=True)

# (原文件名, 视图key, 中文标注, 输出组前缀)
JOBS = [
    ('c8405bc9a5cf7b40f3224ed398a260c1.png', 'front', '正视图 Front', 'group1'),
    ('bfebf0a81e72e8537d49515c94a64534.png', 'side',  '侧视图 Side',  'group1'),
    ('ff9c257dc868ada0e9a3154bba4cf2e6.png', 'top',   '顶视图 Top',   'group1'),
    ('c9743841cdcc11c26afb2057e30bc45c.png', 'front', '正视图 Front', 'group2'),
    ('a0a6ab9c480f0dea7de235448cfb3f95.jpg', 'side',  '侧视图 Side',  'group2'),
    ('8ca0955bcdc7fb6b9a537878030af939.jpg', 'top',   '顶视图 Top',   'group2'),
]

MAX_EDGE = 1024  # 统一最长边

def detect_bg(img_arr):
    """取四角区域中位数作为背景色"""
    h, w = img_arr.shape[:2]
    c = min(60, h//8, w//8)
    corners = np.concatenate([
        img_arr[:c, :c].reshape(-1,3),
        img_arr[:c, -c:].reshape(-1,3),
        img_arr[-c:, :c].reshape(-1,3),
        img_arr[-c:, -c:].reshape(-1,3),
    ])
    return np.median(corners, axis=0)

def remove_bg_and_axis(img_arr, bg):
    """背景纯黑 + 去除高饱和彩色坐标轴，保留白色/浅色曲线（含抗锯齿）"""
    arr = img_arr.astype(np.float32)
    r, g, b = arr[...,0], arr[...,1], arr[...,2]
    mx = np.maximum(np.maximum(r,g), b)
    mn = np.minimum(np.minimum(r,g), b)
    bg_val = float(np.max(bg))

    # 1) 高饱和彩色坐标轴：单通道显著主导另外两通道（红/绿/蓝轴），抗锯齿暗轴/黄绿轴也能抓到
    axis = (
        ((r > g + 15) & (r > b + 15) & (r > 70)) |   # 红轴
        ((g > r + 15) & (g > b + 15) & (g > 70)) |   # 绿轴
        ((b > r + 15) & (b > g + 15) & (b > 70))     # 蓝轴
    )

    # 2) 前景度 alpha：基于亮度与背景的差距，保留抗锯齿平滑过渡
    alpha = np.clip((mx - bg_val) / 130.0, 0.0, 1.0)
    alpha = np.power(alpha, 1.4)  # 稍微压暗中间调，让网格线更黑

    # 3) 合成：前景 * alpha，背景=0；坐标轴强制黑
    out = np.empty_like(arr)
    out[...,0] = np.clip(r * alpha, 0, 255)
    out[...,1] = np.clip(g * alpha, 0, 255)
    out[...,2] = np.clip(b * alpha, 0, 255)
    out[axis] = 0

    # 4) 去除小连通块（3D游标、噪点），保留曲线主体
    gray = np.max(out, axis=2)
    labeled, n = ndimage.label(gray > 8)
    if n > 0:
        sizes = ndimage.sum(np.ones_like(gray), labeled, range(1, n+1))
        keep = np.zeros(n+1, dtype=bool)
        keep[1:] = sizes >= 250  # 小于250像素的连通块去除（游标/噪点）
        out[~keep[labeled]] = 0
    return out.astype(np.uint8)

def add_label(img, text):
    """左上角加白色标注，带半透明黑底"""
    draw = ImageDraw.Draw(img, 'RGBA')
    try:
        font = ImageFont.truetype('msyh.ttc', 28)
    except Exception:
        try:
            font = ImageFont.truetype('arial.ttf', 28)
        except Exception:
            font = ImageFont.load_default()
    pad = 12
    bbox = draw.textbbox((0,0), text, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    x, y = 20, 20
    # 半透明黑底
    draw.rectangle([x-pad, y-pad, x+tw+pad, y+th+pad+4], fill=(0,0,0,160))
    draw.text((x, y), text, fill=(255,255,255,255), font=font)
    return img

results = []
for fname, view, label_cn, group in JOBS:
    src = os.path.join(RAW, fname)
    img = Image.open(src).convert('RGB')
    # 统一尺寸
    w, h = img.size
    scale = MAX_EDGE / max(w, h)
    if scale < 1:
        img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    arr = np.array(img)
    bg = detect_bg(arr)
    cleaned = remove_bg_and_axis(arr, bg)
    out_img = Image.fromarray(cleaned)
    group_cn = '第一组' if group == 'group1' else '第二组'
    out_img = add_label(out_img, f'{group_cn} · {label_cn}')
    out_name = f'{group}_{view}.png'
    out_path = os.path.join(OUT, out_name)
    out_img.save(out_path, 'PNG')
    results.append((out_name, out_img.size, tuple(bg.astype(int))))
    print(f'OK {out_name}  size={out_img.size}  bg={tuple(bg.astype(int))}')

print('\n全部完成，输出目录:', OUT)
