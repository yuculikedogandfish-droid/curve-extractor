"""
图像预处理：从原图中提取金色光带，形态学固化为实心带状，骨架化，修剪毛刺。
"""
import numpy as np
from PIL import Image
from skimage import color, morphology


def load_image(path: str) -> np.ndarray:
    """加载图片为 RGB numpy 数组 (H, W, 3)。"""
    img = Image.open(path).convert("RGB")
    return np.array(img)


def extract_golden_mask(rgb: np.ndarray) -> np.ndarray:
    """
    提取金色光带的二值掩码。
    HSV 锁定黄-橙色相 + 高亮度 + 适度饱和度，亮度兜底。
    """
    hsv = color.rgb2hsv(rgb)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    hue_mask = (h >= 0.05) & (h <= 0.17)
    sat_mask = s >= 0.25
    val_mask = v >= 0.25
    color_mask = hue_mask & sat_mask & val_mask
    bright_mask = v >= 0.70

    return color_mask | bright_mask


def solidify_mask(mask: np.ndarray, close_radius: int = 10, dilate_radius: int = 3, min_object_size: int = 800) -> np.ndarray:
    """
    强力形态学固化：把丝缕状光带变成实心、边缘平滑的带状区域。
    1. 去小连通块  2. 大核闭运算填补空洞  3. 膨胀合并邻近丝缕  4. 再次去噪
    """
    cleaned = morphology.remove_small_objects(mask, min_size=min_object_size)
    cleaned = morphology.binary_closing(cleaned, morphology.disk(close_radius))
    if dilate_radius > 0:
        cleaned = morphology.binary_dilation(cleaned, morphology.disk(dilate_radius))
    cleaned = morphology.remove_small_objects(cleaned, min_size=min_object_size * 2)
    return cleaned


def skeletonize(mask: np.ndarray) -> np.ndarray:
    """骨架化：将实心光带细化为单像素宽的中心线。"""
    return morphology.skeletonize(mask)


def prune_skeleton(skeleton: np.ndarray, min_branch_length: int = 25) -> np.ndarray:
    """
    修剪骨架上的短毛刺分支。
    迭代去除端点开始的短分支，直到没有长度小于阈值的端部分支。
    """
    skel = skeleton.copy()
    h, w = skel.shape

    def get_neighbors(y, x):
        nbs = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and skel[ny, nx]:
                    nbs.append((ny, nx))
        return nbs

    for _ in range(10):
        endpoints = []
        ys, xs = np.where(skel)
        for y, x in zip(ys, xs):
            if len(get_neighbors(y, x)) == 1:
                endpoints.append((y, x))

        removed_any = False
        for ep in endpoints:
            path = [ep]
            current = ep
            prev = None
            while True:
                nbs = get_neighbors(current[0], current[1])
                next_pts = [n for n in nbs if n != prev]
                if not next_pts:
                    break
                if len(get_neighbors(current[0], current[1])) >= 3 and current != ep:
                    break
                nxt = next_pts[0]
                path.append(nxt)
                prev = current
                current = nxt
                if len(path) > min_branch_length:
                    break

            if len(path) <= min_branch_length:
                for p in path[:-1]:
                    skel[p[0], p[1]] = False
                removed_any = True

        if not removed_any:
            break

    return skel
