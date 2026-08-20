"""
曲线平滑：对原始像素点序列做 B 样条参数化拟合，生成 C2 连续平滑曲线。
"""
import numpy as np
from scipy.interpolate import splprep, splev


def smooth_curve(
    points: np.ndarray,
    num_samples: int = 800,
    smooth_factor: float = 150.0,
    k: int = 3,
) -> np.ndarray:
    """
    对原始点序列做 B 样条平滑拟合。
    points: (N, 2)，列为 [y, x]
    返回平滑后的 (num_samples, 2)，列为 [y, x]
    """
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
    """移动平均平滑（兜底方案）。"""
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


def smooth_all_curves(curves: list, num_samples: int = 800, smooth_factor: float = 150.0) -> list:
    """对所有曲线批量平滑。"""
    return [smooth_curve(c, num_samples, smooth_factor) for c in curves]
