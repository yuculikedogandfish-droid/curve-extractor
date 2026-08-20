"""
曲线平滑 v0.8：RDP路径简化 + B样条插值，生成极光滑的宏观走向曲线。

核心思路：
1. RDP (Ramer-Douglas-Peucker) 简化：去掉所有局部锯齿点，只保留宏观拐点
2. B样条插值：用少量拐点插值生成 C2 连续的极光滑曲线
3. 也保留传统的直接B样条平滑方法用于对比
"""
import numpy as np
from scipy.interpolate import splprep, splev


def perpendicular_distance(point: np.ndarray, line_start: np.ndarray, line_end: np.ndarray) -> float:
    """计算点到线段的垂直距离。"""
    if np.array_equal(line_start, line_end):
        return np.linalg.norm(point - line_start)
    # 线段向量
    line_vec = line_end - line_start
    point_vec = point - line_start
    # 投影长度
    proj_len = np.dot(point_vec, line_vec) / np.dot(line_vec, line_vec)
    proj_len = np.clip(proj_len, 0, 1)
    # 最近点
    closest = line_start + proj_len * line_vec
    return np.linalg.norm(point - closest)


def rdp_simplify(points: np.ndarray, epsilon: float = 5.0) -> np.ndarray:
    """
    Ramer-Douglas-Peucker 路径简化算法。
    去掉距离起止点连线小于 epsilon 的所有点，只保留宏观拐点。

    points: (N, 2)，列为 [y, x]
    epsilon: 距离阈值（像素），越大简化越激进，曲线越光滑
    返回简化后的点数组 (M, 2)
    """
    if len(points) < 3:
        return points.copy()

    # 找到距离首尾连线最远的点
    max_dist = 0.0
    max_idx = 0
    for i in range(1, len(points) - 1):
        dist = perpendicular_distance(points[i], points[0], points[-1])
        if dist > max_dist:
            max_dist = dist
            max_idx = i

    # 如果最远距离大于阈值，递归分割
    if max_dist > epsilon:
        left = rdp_simplify(points[:max_idx + 1], epsilon)
        right = rdp_simplify(points[max_idx:], epsilon)
        # 合并（避免重复中间点）
        return np.vstack([left[:-1], right])
    else:
        # 所有点都在阈值内，只保留首尾
        return np.array([points[0], points[-1]])


def smooth_trend_curve(
    points: np.ndarray,
    num_samples: int = 800,
    rdp_epsilon: float = 8.0,
    b_spline_smooth: float = 0.0,
    k: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    生成宏观走向光滑曲线。

    步骤：
    1. RDP 简化原始路径，得到少量宏观拐点
    2. 用拐点做 B 样条插值（smooth=0 表示精确通过拐点）
    3. 重采样到 num_samples 个点

    参数:
        points: 原始点 (N, 2)，列为 [y, x]
        num_samples: 输出采样点数
        rdp_epsilon: RDP 简化阈值（像素），越大越光滑
        b_spline_smooth: B样条平滑因子（0=精确通过拐点，>0=进一步平滑）
        k: B样条阶数

    返回:
        (smoothed_curve, rdp_control_points)
    """
    if len(points) < k + 1:
        return points, points

    # Step 1: RDP 简化
    control = rdp_simplify(points, rdp_epsilon)

    # 确保控制点足够
    if len(control) < k + 1:
        # 简化太激进，回退到直接B样条平滑
        return smooth_curve(points, num_samples, b_spline_smooth or 150.0), points

    # Step 2: B样条插值
    try:
        tck, u = splprep([control[:, 0], control[:, 1]], s=b_spline_smooth, k=k)
        u_new = np.linspace(u.min(), u.max(), num_samples)
        y_smooth, x_smooth = splev(u_new, tck)
        smoothed = np.column_stack([y_smooth, x_smooth])
        return smoothed, control
    except Exception:
        # 插值失败，兜底
        return moving_average_curve(points, num_samples), control


def smooth_curve(
    points: np.ndarray,
    num_samples: int = 800,
    smooth_factor: float = 150.0,
    k: int = 3,
) -> np.ndarray:
    """传统直接B样条平滑（保留用于对比）。"""
    if len(points) < k + 1:
        return points
    y = points[:, 0]
    x = points[:, 1]
    try:
        tck, u = splprep([y, x], s=smooth_factor, k=k)
        u_new = np.linspace(u.min(), u.max(), num_samples)
        y_smooth, x_smooth = splev(u_new, tck)
        return np.column_stack([y_smooth, x_smooth])
    except Exception:
        return moving_average_curve(points, num_samples)


def moving_average_curve(points: np.ndarray, num_samples: int = 800, window: int = 5) -> np.ndarray:
    """移动平均平滑（兜底）。"""
    y = points[:, 0].copy()
    x = points[:, 1].copy()
    kernel = np.ones(window) / window
    y_smooth = np.convolve(y, kernel, mode="same")
    x_smooth = np.convolve(x, kernel, mode="same")
    t = np.linspace(0, 1, len(points))
    t_new = np.linspace(0, 1, num_samples)
    y_resampled = np.interp(t_new, t, y_smooth)
    x_resampled = np.interp(t_new, t, x_smooth)
    return np.column_stack([y_resampled, x_resampled])
