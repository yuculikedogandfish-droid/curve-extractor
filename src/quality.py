"""
曲线质量评估模块：评估提取曲线的光滑度、还原度、长度精度等指标。
"""
import numpy as np


def curve_smoothness(points: np.ndarray) -> dict:
    """
    评估曲线光滑度。
    指标：
    - curvature_std: 曲率标准差（越小越光滑）
    - max_angle_change: 最大角度变化（越小越光滑）
    - avg_angle_change: 平均角度变化
    - c2_continuity: C2 连续性评分（0-1，越高越光滑）
    """
    if len(points) < 5:
        return {"curvature_std": 0, "max_angle_change": 0, "avg_angle_change": 0, "c2_continuity": 1.0}

    # 计算切向量
    tangents = np.diff(points, axis=0)
    tangent_norms = np.linalg.norm(tangents, axis=1, keepdims=True)
    tangent_norms = np.maximum(tangent_norms, 1e-6)
    tangents_norm = tangents / tangent_norms

    # 计算相邻切向量的角度变化
    dot_products = np.sum(tangents_norm[:-1] * tangents_norm[1:], axis=1)
    dot_products = np.clip(dot_products, -1, 1)
    angles = np.arccos(dot_products) * 180 / np.pi

    # 计算曲率（二阶差分）
    second_diff = np.diff(points, n=2, axis=0)
    curvature = np.linalg.norm(second_diff, axis=1)

    # C2 连续性评分：曲率变化越小，C2 连续性越好
    curvature_diff = np.diff(curvature)
    c2_score = 1.0 / (1.0 + np.mean(np.abs(curvature_diff)) * 0.5)

    return {
        "curvature_std": round(float(np.std(curvature)), 4),
        "max_angle_change": round(float(np.max(angles)), 2),
        "avg_angle_change": round(float(np.mean(angles)), 4),
        "c2_continuity": round(float(c2_score), 4),
    }


def curve_reconstruction_error(original_points: np.ndarray, smoothed_points: np.ndarray) -> dict:
    """
    评估平滑曲线对原始路径的还原度。
    将平滑曲线重采样到与原始路径相同的参数空间，计算点到点距离。
    """
    if len(original_points) < 2 or len(smoothed_points) < 2:
        return {"mean_error_px": 0, "max_error_px": 0, "rmse_px": 0}

    # 原始路径的累积弧长参数化
    orig_seg_len = np.sqrt(np.sum(np.diff(original_points, axis=0) ** 2, axis=1))
    orig_cum_len = np.concatenate([[0], np.cumsum(orig_seg_len)])
    orig_total = orig_cum_len[-1] if orig_cum_len[-1] > 0 else 1
    orig_t = orig_cum_len / orig_total

    # 平滑曲线的累积弧长参数化
    smooth_seg_len = np.sqrt(np.sum(np.diff(smoothed_points, axis=0) ** 2, axis=1))
    smooth_cum_len = np.concatenate([[0], np.cumsum(smooth_seg_len)])
    smooth_total = smooth_cum_len[-1] if smooth_cum_len[-1] > 0 else 1
    smooth_t = smooth_cum_len / smooth_total

    # 将平滑曲线重采样到原始路径的参数位置
    y_interp = np.interp(orig_t, smooth_t, smoothed_points[:, 0])
    x_interp = np.interp(orig_t, smooth_t, smoothed_points[:, 1])
    resampled = np.column_stack([y_interp, x_interp])

    # 计算误差
    errors = np.linalg.norm(original_points - resampled, axis=1)

    return {
        "mean_error_px": round(float(np.mean(errors)), 3),
        "max_error_px": round(float(np.max(errors)), 3),
        "rmse_px": round(float(np.sqrt(np.mean(errors ** 2))), 3),
    }


def curve_length_accuracy(original_points: np.ndarray, smoothed_points: np.ndarray) -> dict:
    """评估平滑曲线与原始路径的长度精度。"""
    if len(original_points) < 2 or len(smoothed_points) < 2:
        return {"original_length_px": 0, "smoothed_length_px": 0, "length_error_pct": 0}

    orig_len = float(np.sum(np.sqrt(np.sum(np.diff(original_points, axis=0) ** 2, axis=1))))
    smooth_len = float(np.sum(np.sqrt(np.sum(np.diff(smoothed_points, axis=0) ** 2, axis=1))))
    error_pct = abs(orig_len - smooth_len) / orig_len * 100 if orig_len > 0 else 0

    return {
        "original_length_px": round(orig_len, 2),
        "smoothed_length_px": round(smooth_len, 2),
        "length_error_pct": round(error_pct, 2),
    }


def evaluate_all_curves(curves_data: list) -> dict:
    """
    评估所有曲线的质量，返回汇总报告。
    curves_data: 每个元素包含 "smoothed" (N,2) 和 "raw_points" (M,2)
    """
    report = {"curve_count": len(curves_data), "curves": [], "summary": {}}

    all_smoothness = []
    all_recon_error = []
    all_length_error = []

    for cd in curves_data:
        smoothed = cd["smoothed"]
        raw = cd.get("raw_points", smoothed)

        smooth = curve_smoothness(smoothed)
        recon = curve_reconstruction_error(raw, smoothed)
        length = curve_length_accuracy(raw, smoothed)

        curve_report = {
            "key": cd["key"],
            "name": cd["name"],
            "smoothness": smooth,
            "reconstruction": recon,
            "length_accuracy": length,
        }
        report["curves"].append(curve_report)

        all_smoothness.append(smooth["c2_continuity"])
        all_recon_error.append(recon["rmse_px"])
        all_length_error.append(length["length_error_pct"])

    report["summary"] = {
        "avg_c2_continuity": round(float(np.mean(all_smoothness)), 4) if all_smoothness else 0,
        "min_c2_continuity": round(float(np.min(all_smoothness)), 4) if all_smoothness else 0,
        "avg_rmse_px": round(float(np.mean(all_recon_error)), 3) if all_recon_error else 0,
        "max_rmse_px": round(float(np.max(all_recon_error)), 3) if all_recon_error else 0,
        "avg_length_error_pct": round(float(np.mean(all_length_error)), 2) if all_length_error else 0,
        "overall_quality_score": round(float(
            np.mean(all_smoothness) * 0.4 +
            (1.0 / (1.0 + np.mean(all_recon_error))) * 0.3 +
            (1.0 - np.mean(all_length_error) / 100) * 0.3
        ), 4) if all_smoothness else 0,
    }

    return report


def print_quality_report(report: dict):
    """打印质量评估报告到控制台。"""
    print("\n" + "=" * 60)
    print("曲线质量评估报告")
    print("=" * 60)
    for cr in report["curves"]:
        print(f"\n  [{cr['key']}] {cr['name']}")
        print(f"    光滑度 (C2连续性): {cr['smoothness']['c2_continuity']:.4f}")
        print(f"    最大角度变化: {cr['smoothness']['max_angle_change']:.2f}°")
        print(f"    还原度 (RMSE): {cr['reconstruction']['rmse_px']:.3f} px")
        print(f"    长度误差: {cr['length_accuracy']['length_error_pct']:.2f}%")
    print("\n" + "-" * 60)
    s = report["summary"]
    print(f"  平均 C2 连续性: {s['avg_c2_continuity']:.4f}")
    print(f"  平均 RMSE: {s['avg_rmse_px']:.3f} px")
    print(f"  平均长度误差: {s['avg_length_error_pct']:.2f}%")
    print(f"  综合质量评分: {s['overall_quality_score']:.4f} / 1.0")
    print("=" * 60 + "\n")
