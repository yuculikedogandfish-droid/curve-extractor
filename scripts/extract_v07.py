#!/usr/bin/env python3
"""
曲线提取主入口 v0.7（稳定版）
方法：多源 BFS 最短路径 + 端点角度聚类 → 精确提取5根主枝条 → B样条平滑 → SVG/JSON导出。
"""
import sys
import os
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.preprocess import load_image, extract_golden_mask, solidify_mask, skeletonize, prune_skeleton
from src.trace_angle import extract_5_main_curves
from src.smooth import smooth_curve
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def export_svg(curves_data: list, image_size: tuple, output_path: str):
    """导出5根主枝条为 SVG，每根不同颜色。"""
    w, h = image_size
    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]
    parts = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'  <rect width="100%" height="100%" fill="black"/>',
    ]
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        d = f"M {pts[0,1]:.1f} {pts[0,0]:.1f}"
        for p in pts[1:]:
            d += f" L {p[1]:.1f} {p[0]:.1f}"
        parts.append(
            f'  <path d="{d}" fill="none" stroke="{colors[i % len(colors)]}" '
            f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" '
            f'id="{cd["key"]}" name="{cd["name"]}"/>'
        )
    parts.append("</svg>")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def export_json(curves_data: list, output_path: str):
    """导出JSON，包含每根枝条的名称、平滑点坐标、长度。"""
    data = {"version": "v0.7", "curve_count": len(curves_data), "curves": []}
    for cd in curves_data:
        pts = cd["smoothed"]
        points_xy = [[float(p[1]), float(p[0])] for p in pts]
        lengths = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
        data["curves"].append({
            "key": cd["key"],
            "name": cd["name"],
            "point_count": len(pts),
            "total_length_px": round(float(np.sum(lengths)), 2),
            "raw_length": cd["length"],
            "endpoint_xy": [float(cd["endpoint"][1]), float(cd["endpoint"][0])],
            "angle_deg": round(float(cd["angle"]), 1),
            "points": points_xy,
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_preview(curves_data: list, original: np.ndarray, output_path: str):
    """生成预览图：左原图叠加，右独立曲线。"""
    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]
    fig, axes = plt.subplots(1, 2, figsize=(18, 8))

    axes[0].imshow(original, alpha=0.6)
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        axes[0].plot(pts[:, 1], pts[:, 0], color=colors[i], linewidth=2.5, label=cd["name"])
        axes[0].scatter(cd["endpoint"][1], cd["endpoint"][0], color=colors[i], s=80, marker="*", edgecolors="white", linewidths=1)
    axes[0].set_title("5 Main Curves Overlay on Original", fontsize=13)
    axes[0].legend(loc="upper right", fontsize=9, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[0].axis("off")

    axes[1].set_facecolor("black")
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        axes[1].plot(pts[:, 1], pts[:, 0], color=colors[i], linewidth=2.5, label=cd["name"])
    axes[1].set_title("5 Extracted Smooth Curves", fontsize=13)
    axes[1].set_aspect("equal")
    axes[1].invert_yaxis()
    axes[1].legend(loc="upper right", fontsize=9, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[1].axis("off")

    fig.suptitle("Curve Extraction v0.7 — Angle-Clustered 5 Main Branches", fontsize=15, color="white", fontweight="bold")
    fig.patch.set_facecolor("#1a1a1a")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)


def main():
    VERSION = "v0.7"
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_path = os.path.join(base_dir, "input", "original.png")
    output_dir = os.path.join(base_dir, "output", VERSION)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print(f"Curve Extractor {VERSION} — BFS + Angle Clustering (5 curves)")
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
        skel_pruned,
        min_length=80,
        root_y_ratio=0.72,
        center_y_ratio=0.65,
        center_x_ratio=0.50,
    )

    print("\n[3/5] B-spline smoothing...")
    for cd in curves_data:
        cd["smoothed"] = smooth_curve(cd["points"], num_samples=800, smooth_factor=150.0)
        print(f"  {cd['name']:8s}: {cd['length']} raw pts -> {len(cd['smoothed'])} smooth pts")

    print("\n[4/5] Exporting SVG / JSON...")
    svg_path = os.path.join(output_dir, "curves_5branches.svg")
    json_path = os.path.join(output_dir, "curves_5branches.json")
    preview_path = os.path.join(output_dir, "preview.png")

    export_svg(curves_data, (w, h), svg_path)
    export_json(curves_data, json_path)

    print("\n[5/5] Generating preview...")
    make_preview(curves_data, original, preview_path)

    print(f"\n  SVG:     {svg_path}")
    print(f"  JSON:    {json_path}")
    print(f"  Preview: {preview_path}")

    print("\n" + "=" * 60)
    print(f"Done! {VERSION} — 5 main branches extracted.")
    print("=" * 60)


if __name__ == "__main__":
    main()
