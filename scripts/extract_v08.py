#!/usr/bin/env python3
"""
曲线提取主入口 v0.8 — 宏观走向光滑曲线
核心改进：RDP路径简化(去锯齿) → B样条插值拐点 → 极光滑曲线
同时生成 v0.7(直接B样条) vs v0.8(RDP+插值) 对比图
"""
import sys
import os
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.preprocess import load_image, extract_golden_mask, solidify_mask, skeletonize, prune_skeleton
from src.trace_angle import extract_5_main_curves
from src.smooth import smooth_trend_curve, smooth_curve
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


CURVE_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]


def export_svg(curves_data: list, image_size: tuple, output_path: str):
    w, h = image_size
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '  <rect width="100%" height="100%" fill="black"/>',
    ]
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        d = f"M {pts[0,1]:.1f} {pts[0,0]:.1f}"
        for p in pts[1:]:
            d += f" L {p[1]:.1f} {p[0]:.1f}"
        parts.append(
            f'  <path d="{d}" fill="none" stroke="{CURVE_COLORS[i % len(CURVE_COLORS)]}" '
            f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" '
            f'id="{cd["key"]}" name="{cd["name"]}"/>'
        )
    parts.append("</svg>")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def export_json(curves_data: list, output_path: str, version: str):
    data = {"version": version, "curve_count": len(curves_data), "curves": []}
    for cd in curves_data:
        pts = cd["smoothed"]
        points_xy = [[float(p[1]), float(p[0])] for p in pts]
        lengths = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
        control_xy = [[float(p[1]), float(p[0])] for p in cd.get("control", [])]
        data["curves"].append({
            "key": cd["key"],
            "name": cd["name"],
            "point_count": len(pts),
            "total_length_px": round(float(np.sum(lengths)), 2),
            "raw_length": cd["length"],
            "rdp_control_points": len(control_xy),
            "control_points": control_xy,
            "endpoint_xy": [float(cd["endpoint"][1]), float(cd["endpoint"][0])],
            "angle_deg": round(float(cd["angle"]), 1),
            "points": points_xy,
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_comparison(curves_data: list, original: np.ndarray, output_path: str):
    """生成 v0.7(直接B样条) vs v0.8(RDP+插值) 对比图。"""
    fig, axes = plt.subplots(1, 3, figsize=(24, 7))

    # 左：原图叠加 v0.8 光滑曲线
    axes[0].imshow(original, alpha=0.5)
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        axes[0].plot(pts[:, 1], pts[:, 0], color=CURVE_COLORS[i], linewidth=2.5, label=cd["name"])
    axes[0].set_title("v0.8: RDP + B-Spline (Overlay)", fontsize=13)
    axes[0].legend(loc="upper right", fontsize=8, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[0].axis("off")

    # 中：v0.8 独立曲线 + RDP拐点
    axes[1].set_facecolor("black")
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        ctrl = cd.get("control", [])
        axes[1].plot(pts[:, 1], pts[:, 0], color=CURVE_COLORS[i], linewidth=2.5, label=cd["name"])
        if len(ctrl) > 0:
            axes[1].scatter(ctrl[:, 1], ctrl[:, 0], color=CURVE_COLORS[i], s=30, marker="o",
                           edgecolors="white", linewidths=0.5, zorder=5)
    axes[1].set_title("v0.8 Smooth Curves + RDP Control Points", fontsize=13)
    axes[1].set_aspect("equal")
    axes[1].invert_yaxis()
    axes[1].legend(loc="upper right", fontsize=8, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[1].axis("off")

    # 右：v0.7 直接B样条（用于对比）
    axes[2].set_facecolor("black")
    for i, cd in enumerate(curves_data):
        old_smooth = smooth_curve(cd["points"], num_samples=800, smooth_factor=150.0)
        axes[2].plot(old_smooth[:, 1], old_smooth[:, 0], color=CURVE_COLORS[i], linewidth=2.5, label=cd["name"])
    axes[2].set_title("v0.7: Direct B-Spline (for comparison)", fontsize=13)
    axes[2].set_aspect("equal")
    axes[2].invert_yaxis()
    axes[2].legend(loc="upper right", fontsize=8, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[2].axis("off")

    fig.suptitle("Curve Extraction v0.8 — RDP Simplification + B-Spline Interpolation (Ultra-Smooth Trend Lines)",
                 fontsize=15, color="white", fontweight="bold")
    fig.patch.set_facecolor("#1a1a1a")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def main():
    VERSION = "v0.8"
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_path = os.path.join(base_dir, "input", "original.png")
    output_dir = os.path.join(base_dir, "output", VERSION)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"Curve Extractor {VERSION} — RDP + B-Spline Ultra-Smooth Trend")
    print("=" * 60)

    print("\n[1/5] Loading & preprocessing...")
    original = load_image(input_path)
    h, w = original.shape[:2]
    print(f"  Image: {w} x {h}")

    mask = extract_golden_mask(original)
    solid = solidify_mask(mask, close_radius=10, dilate_radius=3, min_object_size=800)
    skel = skeletonize(solid)
    skel_pruned = prune_skeleton(skel, min_branch_length=25)
    print(f"  Skeleton (pruned): {skel_pruned.sum()} pixels")

    print("\n[2/5] Extracting 5 main curves via angle clustering...")
    curves_data = extract_5_main_curves(
        skel_pruned, min_length=80, root_y_ratio=0.72,
        center_y_ratio=0.65, center_x_ratio=0.50,
    )

    print("\n[3/5] RDP simplify + B-spline interpolation (epsilon=8.0)...")
    for cd in curves_data:
        smoothed, control = smooth_trend_curve(
            cd["points"], num_samples=800, rdp_epsilon=8.0, b_spline_smooth=0.0
        )
        cd["smoothed"] = smoothed
        cd["control"] = control
        print(f"  {cd['name']:8s}: {cd['length']} raw pts -> {len(control)} RDP control pts -> {len(smoothed)} smooth pts")

    print("\n[4/5] Exporting SVG / JSON / comparison...")
    svg_path = os.path.join(output_dir, "curves_5branches.svg")
    json_path = os.path.join(output_dir, "curves_5branches.json")
    comp_path = os.path.join(output_dir, "comparison_v07_vs_v08.png")

    export_svg(curves_data, (w, h), svg_path)
    export_json(curves_data, json_path, VERSION)
    make_comparison(curves_data, original, comp_path)

    print(f"  SVG:        {svg_path}")
    print(f"  JSON:       {json_path}")
    print(f"  Comparison: {comp_path}")

    print("\n" + "=" * 60)
    print(f"Done! {VERSION} — ultra-smooth trend curves generated.")
    print("=" * 60)


if __name__ == "__main__":
    main()
