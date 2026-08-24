"""
智能曲线追踪模块 - 全自动端点对追踪
不固定曲线数量，自动检测骨架中所有端点，从端点对追踪完整曲线。
适用于复杂交织的光效图案。
"""

import numpy as np
from collections import deque


def find_endpoints_and_junctions(skeleton, w, h):
    """检测骨架中的所有端点（度=1）和分支点（度>2）"""
    endpoints = []
    junctions = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if not skeleton[y * w + x]:
                continue
            # 计算8邻域度数
            degree = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and skeleton[ny * w + nx]:
                        degree += 1
            if degree == 1:
                endpoints.append((y, x))
            elif degree > 2:
                junctions.append((y, x))
    return endpoints, junctions


def trace_between_endpoints(start, skeleton, w, h, visited, max_len=5000):
    """
    从一个端点出发，BFS追踪到最近的另一个端点。
    不经过已访问的像素。返回路径和终点。
    """
    sy, sx = start
    # BFS
    dist = np.full(h * w, -1, dtype=np.int32)
    parent = np.full(h * w, -1, dtype=np.int32)
    queue = deque()
    start_idx = sy * w + sx
    dist[start_idx] = 0
    queue.append(start_idx)

    found_end = -1
    while queue:
        idx = queue.popleft()
        y, x = idx // w, idx % w
        d = dist[idx]
        if d > max_len:
            break
        # 检查是否是另一个端点（不是起点）
        if idx != start_idx:
            # 计算度数
            degree = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and skeleton[ny * w + nx]:
                        degree += 1
            if degree == 1:
                found_end = idx
                break
        # 扩展邻居
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if ny < 0 or ny >= h or nx < 0 or nx >= w:
                    continue
                nidx = ny * w + nx
                if not skeleton[nidx] or visited[nidx] or dist[nidx] >= 0:
                    continue
                dist[nidx] = d + 1
                parent[nidx] = idx
                queue.append(nidx)

    if found_end < 0:
        return None, None

    # 回溯路径
    path = []
    idx = found_end
    while idx >= 0:
        path.append((idx // w, idx % w))
        idx = parent[idx]
    path.reverse()
    return path, (found_end // w, found_end % w)


def trace_all_curves_smart(skeleton, w, h, min_length=50, max_curves=50):
    """
    全自动智能追踪所有曲线。
    1. 检测所有端点
    2. 从每个端点出发，追踪到最近的另一个端点
    3. 标记路径为已访问
    4. 过滤太短的曲线
    返回曲线列表，每条曲线是 [(y,x), ...] 点序列。
    """
    visited = np.zeros(h * w, dtype=bool)
    endpoints, junctions = find_endpoints_and_junctions(skeleton, w, h)

    print(f"  [Smart Trace] 检测到 {len(endpoints)} 个端点, {len(junctions)} 个分支点")

    curves = []
    used_endpoints = set()

    for i, ep in enumerate(endpoints):
        ep_idx = ep[0] * w + ep[1]
        if visited[ep_idx] or ep in used_endpoints:
            continue

        # 从这个端点出发追踪
        path, end_point = trace_between_endpoints(ep, skeleton, w, h, visited)

        if path is None or len(path) < min_length:
            continue

        # 标记路径为已访问
        for (y, x) in path:
            visited[y * w + x] = True

        # 标记终点为已使用
        if end_point:
            used_endpoints.add(end_point)

        curves.append(path)

        if len(curves) >= max_curves:
            break

    print(f"  [Smart Trace] 提取到 {len(curves)} 条曲线 (长度>={min_length})")

    # 按长度降序排序
    curves.sort(key=len, reverse=True)
    return curves


def trace_all_curves_by_components(skeleton, w, h, min_length=50):
    """
    基于连通分量的曲线提取。
    每个连通分量提取一条主曲线（从一端到另一端的最长路径）。
    适用于曲线相对独立的情况。
    """
    visited = np.zeros(h * w, dtype=bool)
    curves = []

    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if not skeleton[idx] or visited[idx]:
                continue

            # BFS找到整个连通分量
            component = []
            queue = deque([idx])
            visited[idx] = True
            while queue:
                cidx = queue.popleft()
                component.append(cidx)
                cy, cx = cidx // w, cidx % w
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            nidx = ny * w + nx
                            if skeleton[nidx] and not visited[nidx]:
                                visited[nidx] = True
                                queue.append(nidx)

            if len(component) < min_length:
                continue

            # 在连通分量中找两个最远的端点（直径）
            # 简化：从分量中第一个点BFS找最远点，再从最远点BFS找另一个最远点
            def bfs_farthest(start_idx):
                dist_map = {start_idx: 0}
                q = deque([start_idx])
                farthest = start_idx
                max_d = 0
                while q:
                    cidx = q.popleft()
                    d = dist_map[cidx]
                    if d > max_d:
                        max_d = d
                        farthest = cidx
                    cy, cx = cidx // w, cidx % w
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dy == 0 and dx == 0:
                                continue
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w:
                                nidx = ny * w + nx
                                if skeleton[nidx] and nidx not in dist_map:
                                    dist_map[nidx] = d + 1
                                    q.append(nidx)
                return farthest, max_d, dist_map

            # 两次BFS找直径端点
            ep1, _, _ = bfs_farthest(component[0])
            ep2, _, dist_map = bfs_farthest(ep1)

            # 回溯路径
            path = []
            idx = ep2
            while idx in dist_map:
                path.append((idx // w, idx % w))
                if idx == ep1:
                    break
                # 找父节点（距离减1的邻居）
                d = dist_map[idx]
                cy, cx = idx // w, idx % w
                found_parent = False
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            nidx = ny * w + nx
                            if nidx in dist_map and dist_map[nidx] == d - 1:
                                idx = nidx
                                found_parent = True
                                break
                    if found_parent:
                        break
                if not found_parent:
                    break
            path.reverse()

            if len(path) >= min_length:
                curves.append(path)

    print(f"  [Component Trace] 提取到 {len(curves)} 条曲线 (按连通分量)")
    curves.sort(key=len, reverse=True)
    return curves
