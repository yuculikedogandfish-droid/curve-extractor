"""
骨架曲线追踪：基于多源 BFS 最短路径 + 端点角度聚类，精确提取5根主枝条。

核心思路：
1. 多源 BFS 从底部根区域计算每个骨架像素到根的距离场
2. 每个端点沿距离递减方向走到根 → 最短路径
3. 按端点相对于汇聚中心的角度聚类为5组（左上/左下/中上/右上/右下）
4. 每组取最长路径 → 5根主枝条
"""
import numpy as np
from collections import deque


def _neighbors(y: int, x: int, h: int, w: int) -> list:
    nbs = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                nbs.append((ny, nx))
    return nbs


def _degree_map(skeleton: np.ndarray) -> np.ndarray:
    h, w = skeleton.shape
    degree = np.zeros((h, w), dtype=np.int32)
    ys, xs = np.where(skeleton)
    for y, x in zip(ys, xs):
        cnt = sum(1 for ny, nx in _neighbors(y, x, h, w) if skeleton[ny, nx])
        degree[y, x] = cnt
    return degree


def find_endpoints(skeleton: np.ndarray) -> list:
    deg = _degree_map(skeleton)
    ys, xs = np.where((skeleton) & (deg == 1))
    return list(zip(ys, xs))


def define_root_region(skeleton: np.ndarray, y_ratio: float = 0.72) -> np.ndarray:
    h, w = skeleton.shape
    y_min = int(h * y_ratio)
    root_mask = np.zeros_like(skeleton, dtype=bool)
    root_mask[y_min:, :] = True
    return root_mask & skeleton


def multi_source_bfs(skeleton: np.ndarray, sources: list) -> np.ndarray:
    h, w = skeleton.shape
    dist = np.full((h, w), -1, dtype=np.int32)
    queue = deque()
    for sy, sx in sources:
        if skeleton[sy, sx] and dist[sy, sx] == -1:
            dist[sy, sx] = 0
            queue.append((sy, sx))
    while queue:
        y, x = queue.popleft()
        d = dist[y, x]
        for ny, nx in _neighbors(y, x, h, w):
            if skeleton[ny, nx] and dist[ny, nx] == -1:
                dist[ny, nx] = d + 1
                queue.append((ny, nx))
    return dist


def trace_path_to_root(start: tuple, dist: np.ndarray, skeleton: np.ndarray) -> list:
    h, w = skeleton.shape
    path = [start]
    visited = {start}
    current = start
    while True:
        y, x = current
        if dist[y, x] == 0:
            break
        candidates = [(ny, nx) for ny, nx in _neighbors(y, x, h, w)
                      if skeleton[ny, nx] and (ny, nx) not in visited and dist[ny, nx] >= 0]
        if not candidates:
            candidates = [(ny, nx) for ny, nx in _neighbors(y, x, h, w)
                          if skeleton[ny, nx] and (ny, nx) not in visited]
            if not candidates:
                break
        best = min(candidates, key=lambda p: dist[p[0], p[1]])
        path.append(best)
        visited.add(best)
        current = best
        if len(path) > 2000:
            break
    return path


# 5个角度区间（度），对应5根主枝条
# 角度定义：arctan2(ey-cy, ex-cx)，正右=0°，正上=-90°，正左=±180°
ANGLE_GROUPS = {
    "right_lower":  {"name": "右下卷曲枝", "min": -25, "max": 15},
    "right_upper":  {"name": "右上大枝",   "min": -75, "max": -35},
    "center_top":   {"name": "中间主干",   "min": -105, "max": -75},
    "left_upper":   {"name": "左上大枝",   "min": -155, "max": -110},
    "left_lower":   {"name": "左下卷曲枝", "min": -180, "max": -155},
}


def extract_5_main_curves(
    skeleton: np.ndarray,
    min_length: int = 80,
    root_y_ratio: float = 0.72,
    center_y_ratio: float = 0.65,
    center_x_ratio: float = 0.50,
) -> list:
    """
    提取5根主枝条，按端点角度聚类。
    返回列表，每个元素为 dict:
        {"key": str, "name": str, "points": np.ndarray (N,2), "endpoint": (y,x), "length": int, "angle": float}
    """
    h, w = skeleton.shape
    cy = h * center_y_ratio
    cx = w * center_x_ratio

    print(f"  [AngleCluster] Center=({cx:.0f},{cy:.0f}), root y>={root_y_ratio:.0%}")

    root_mask = define_root_region(skeleton, y_ratio=root_y_ratio)
    root_pixels = list(zip(*np.where(root_mask)))
    print(f"  [AngleCluster] Root pixels: {len(root_pixels)}")
    dist = multi_source_bfs(skeleton, root_pixels)

    endpoints = find_endpoints(skeleton)
    print(f"  [AngleCluster] Endpoints: {len(endpoints)}")

    endpoint_paths = []
    for ep in endpoints:
        if dist[ep[0], ep[1]] < 0:
            continue
        path = trace_path_to_root(ep, dist, skeleton)
        if len(path) < min_length:
            continue
        ey, ex = ep
        angle = np.degrees(np.arctan2(ey - cy, ex - cx))
        endpoint_paths.append((angle, ep, np.array(path, dtype=np.float64)))

    print(f"  [AngleCluster] Valid paths (len>={min_length}): {len(endpoint_paths)}")

    results = []
    for key, group in ANGLE_GROUPS.items():
        amin, amax = group["min"], group["max"]
        if amin <= -180:
            matched = [(a, ep, p) for a, ep, p in endpoint_paths
                       if (a >= amin and a <= amax) or (a >= 160 and a <= 180)]
        else:
            matched = [(a, ep, p) for a, ep, p in endpoint_paths
                       if amin <= a <= amax]

        if matched:
            matched.sort(key=lambda x: len(x[2]), reverse=True)
            best_angle, best_ep, best_path = matched[0]
            results.append({
                "key": key,
                "name": group["name"],
                "points": best_path,
                "endpoint": best_ep,
                "length": len(best_path),
                "angle": best_angle,
                "group_count": len(matched),
            })
            print(f"  [AngleCluster] {group['name']:8s}: {len(matched)} candidates, "
                  f"best len={len(best_path)}, angle={best_angle:.1f}°")
        else:
            print(f"  [AngleCluster] {group['name']:8s}: NO candidates in [{amin},{amax}]!")

    return results
