#!/usr/bin/env python3
"""
Curve Extractor 主入口 v1.0 — 增强版
支持：命令行参数化、批量处理、多格式导出、质量评估、中间结果可视化

用法示例：
  # 基本用法（使用默认参数）
  python scripts/extract.py --input input/original.png --output output/

  # 指定参数
  python scripts/extract.py -i input/original.png -o output/ \\
      --hsv-hue 0.05 0.17 --hsv-sat 0.25 --hsv-val 0.25 \\
      --close-radius 10 --dilate-radius 3 --min-object-size 800 \\
      --root-y-ratio 0.72 --center-y-ratio 0.65 \\
      --rdp-epsilon 8.0 --num-samples 800 \\
      --export svg json csv dxf obj ue_spline niagara ue_script \\
      --quality-report

  # 批量处理
  python scripts/extract.py --batch input/*.png --output output/
"""
import sys
import os
import argparse
import glob
import json
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.preprocess import load_image, extract_golden_mask, solidify_mask, skeletonize, prune_skeleton
from src.trace_angle import extract_5_main_curves
from src.trace_smart import trace_all_curves_smart
from src.smooth import smooth_trend_curve
from src.export import (
    export_svg, export_json, export_csv, export_dxf, export_obj,
    export_ue_spline, export_niagara_path, generate_ue_import_script,
)
from src.quality import evaluate_all_curves, print_quality_report

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 修复中文字体
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


CURVE_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]


def parse_args():
    parser = argparse.ArgumentParser(description="Curve Extractor — 金色光带曲线提取工具")
    parser.add_argument("-i", "--input", type=str, help="输入图片路径")
    parser.add_argument("-o", "--output", type=str, default="output", help="输出目录")
    parser.add_argument("--batch", type=str, nargs="+", help="批量处理：多个输入图片路径或通配符")
    parser.add_argument("--version", type=str, default="v1.0", help="版本号")

    # HSV 参数
    hsv = parser.add_argument_group("HSV 掩码参数")
    hsv.add_argument("--hsv-hue", type=float, nargs=2, default=[0.05, 0.17], metavar=("MIN", "MAX"), help="色相范围")
    hsv.add_argument("--hsv-sat", type=float, default=0.25, help="最小饱和度")
    hsv.add_argument("--hsv-val", type=float, default=0.25, help="最小亮度")
    hsv.add_argument("--hsv-bright", type=float, default=0.70, help="亮度兜底阈值")

    # 形态学参数
    morph = parser.add_argument_group("形态学固化参数")
    morph.add_argument("--close-radius", type=int, default=10, help="闭运算核半径")
    morph.add_argument("--dilate-radius", type=int, default=3, help="膨胀核半径")
    morph.add_argument("--min-object-size", type=int, default=800, help="最小连通块面积")
    morph.add_argument("--prune-length", type=int, default=25, help="修剪短毛刺长度")

    # 追踪参数
    trace = parser.add_argument_group("曲线追踪参数")
    trace.add_argument("--trace-mode", type=str, default="angle", choices=["angle", "smart"],
                       help="追踪模式：angle=固定5根角度聚类(默认)，smart=全自动智能追踪(适用于复杂图片)")
    trace.add_argument("--max-curves", type=int, default=50, help="智能追踪模式下最大曲线数")
    trace.add_argument("--root-y-ratio", type=float, default=0.72, help="根区域 Y 比例(angle模式)")
    trace.add_argument("--center-y-ratio", type=float, default=0.65, help="汇聚中心 Y 比例(angle模式)")
    trace.add_argument("--center-x-ratio", type=float, default=0.50, help="汇聚中心 X 比例(angle模式)")
    trace.add_argument("--min-length", type=int, default=80, help="最小路径长度")

    # 平滑参数
    smooth = parser.add_argument_group("曲线平滑参数")
    smooth.add_argument("--rdp-epsilon", type=float, default=8.0, help="RDP 简化阈值（像素）")
    smooth.add_argument("--num-samples", type=int, default=800, help="输出采样点数")
    smooth.add_argument("--b-spline-smooth", type=float, default=0.0, help="B样条平滑因子")
    smooth.add_argument("--b-spline-k", type=int, default=3, help="B样条阶数")

    # 导出参数
    export_group = parser.add_argument_group("导出参数")
    export_group.add_argument("--export", type=str, nargs="+",
                              default=["svg", "json"],
                              choices=["svg", "json", "csv", "dxf", "obj", "ue_spline", "niagara", "ue_script"],
                              help="导出格式列表")
    export_group.add_argument("--world-scale", type=float, default=0.1, help="UE 世界缩放比例")
    export_group.add_argument("--stroke-width", type=float, default=3.0, help="SVG 线宽")
    export_group.add_argument("--show-control-points", action="store_true", help="SVG 显示 RDP 拐点")

    # 可视化参数
    vis = parser.add_argument_group("可视化参数")
    vis.add_argument("--save-intermediate", action="store_true", help="保存中间结果（掩码、骨架、BFS距离场）")
    vis.add_argument("--quality-report", action="store_true", help="生成质量评估报告")
    vis.add_argument("--comparison", action="store_true", help="生成对比图")

    return parser.parse_args()


def save_intermediate_results(rgb, mask, skeleton, dist, output_dir, name_prefix):
    """保存中间结果可视化。"""
    inter_dir = os.path.join(output_dir, "intermediate")
    os.makedirs(inter_dir, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))

    axes[0, 0].imshow(rgb)
    axes[0, 0].set_title("Original Image", fontsize=12)
    axes[0, 0].axis("off")

    axes[0, 1].imshow(mask, cmap="gray")
    axes[0, 1].set_title("Golden Mask (HSV)", fontsize=12)
    axes[0, 1].axis("off")

    axes[1, 0].imshow(skeleton, cmap="gray")
    axes[1, 0].set_title("Skeleton (Pruned)", fontsize=12)
    axes[1, 0].axis("off")

    if dist is not None:
        dist_vis = np.where(dist >= 0, dist, 0)
        im = axes[1, 1].imshow(dist_vis, cmap="viridis")
        axes[1, 1].set_title("BFS Distance Field (from root)", fontsize=12)
        axes[1, 1].axis("off")
        plt.colorbar(im, ax=axes[1, 1], fraction=0.046)
    else:
        axes[1, 1].set_title("(no distance field)", fontsize=12)
        axes[1, 1].axis("off")

    plt.tight_layout()
    plt.savefig(os.path.join(inter_dir, f"{name_prefix}_pipeline.png"), dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  [Intermediate] Saved pipeline visualization")


def make_comparison_figure(curves_data, original, output_path):
    """生成对比图：原图叠加 + 独立曲线 + RDP拐点。"""
    n_curves = len(curves_data)
    # 使用 colormap 生成足够多的颜色
    try:
        cmap = plt.colormaps.get_cmap("tab20")
    except AttributeError:
        cmap = plt.cm.get_cmap("tab20")
    curve_colors = [cmap(i % 20) for i in range(n_curves)]

    fig, axes = plt.subplots(1, 3, figsize=(24, 7))

    axes[0].imshow(original, alpha=0.5)
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        axes[0].plot(pts[:, 1], pts[:, 0], color=curve_colors[i], linewidth=2.5, label=cd["name"])
    axes[0].set_title(f"Smooth Curves Overlay on Original ({n_curves} curves)", fontsize=13)
    if n_curves <= 15:
        axes[0].legend(loc="upper right", fontsize=8, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[0].axis("off")

    axes[1].set_facecolor("black")
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        axes[1].plot(pts[:, 1], pts[:, 0], color=curve_colors[i], linewidth=2.5, label=cd["name"])
    axes[1].set_title(f"Smooth Curves (Isolated, {n_curves} curves)", fontsize=13)
    axes[1].set_aspect("equal")
    axes[1].invert_yaxis()
    if n_curves <= 15:
        axes[1].legend(loc="upper right", fontsize=8, facecolor="black", labelcolor="white", framealpha=0.8)
    axes[1].axis("off")

    axes[2].set_facecolor("black")
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        ctrl = cd.get("control", [])
        axes[2].plot(pts[:, 1], pts[:, 0], color=curve_colors[i], linewidth=2, alpha=0.7)
        if len(ctrl) > 0:
            axes[2].scatter(ctrl[:, 1], ctrl[:, 0], color=curve_colors[i], s=40, marker="o",
                           edgecolors="white", linewidths=0.8, zorder=5)
    axes[2].set_title("RDP Control Points (Macro Inflection Points)", fontsize=13)
    axes[2].set_aspect("equal")
    axes[2].invert_yaxis()
    axes[2].axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def process_single_image(input_path, output_dir, args, name_prefix=None):
    """处理单张图片。"""
    if name_prefix is None:
        name_prefix = os.path.splitext(os.path.basename(input_path))[0]

    print(f"\n{'='*60}")
    print(f"Processing: {input_path}")
    print(f"{'='*60}")

    # 1. 加载图片
    print("\n[1/5] Loading image...")
    rgb = load_image(input_path)
    h, w = rgb.shape[:2]
    print(f"  Image size: {w} x {h}")

    # 2. 预处理
    print("\n[2/5] Preprocessing (HSV mask + solidify + skeleton + prune)...")
    mask = extract_golden_mask(rgb)
    print(f"  Mask pixels: {np.sum(mask)} ({np.sum(mask)/(h*w)*100:.1f}%)")
    solid = solidify_mask(mask, close_radius=args.close_radius, dilate_radius=args.dilate_radius,
                           min_object_size=args.min_object_size)
    print(f"  After solidify: {np.sum(solid)} pixels")
    skeleton = skeletonize(solid)
    print(f"  Skeleton pixels: {np.sum(skeleton)}")
    skeleton_pruned = prune_skeleton(skeleton, min_branch_length=args.prune_length)
    print(f"  After prune: {np.sum(skeleton_pruned)} pixels")

    # 3. 追踪曲线
    if args.trace_mode == "smart":
        print("\n[3/5] Tracing curves (smart endpoint-pair tracing)...")
        skeleton_1d = skeleton_pruned.flatten()
        raw_curves_xy = trace_all_curves_smart(
            skeleton_1d, w, h,
            min_length=args.min_length,
            max_curves=args.max_curves,
        )
        # 转换为与 angle 模式相同的格式
        raw_curves = []
        for i, curve in enumerate(raw_curves_xy):
            pts_arr = np.array(curve)  # [(y,x), ...]
            start_y, start_x = curve[0]
            end_y, end_x = curve[-1]
            angle = np.degrees(np.arctan2(end_y - start_y, end_x - start_x))
            raw_curves.append({
                "key": f"curve_{i+1:02d}",
                "name": f"Curve {i+1}",
                "points": pts_arr,
                "length": len(curve),
                "endpoint": pts_arr[-1],
                "angle": angle,
            })
        print(f"  Extracted {len(raw_curves)} curves (smart mode)")
    else:
        print("\n[3/5] Tracing curves (multi-source BFS + angle clustering)...")
        raw_curves = extract_5_main_curves(
            skeleton_pruned,
            min_length=args.min_length,
            root_y_ratio=args.root_y_ratio,
            center_y_ratio=args.center_y_ratio,
            center_x_ratio=args.center_x_ratio,
        )
        print(f"  Extracted {len(raw_curves)} main curves")

    # 4. 平滑
    print("\n[4/5] Smoothing (RDP simplify + B-spline interpolation)...")
    curves_data = []
    for cd in raw_curves:
        smoothed, control = smooth_trend_curve(
            cd["points"],
            num_samples=args.num_samples,
            rdp_epsilon=args.rdp_epsilon,
            b_spline_smooth=args.b_spline_smooth,
            k=args.b_spline_k,
        )
        curves_data.append({
            "key": cd["key"], "name": cd["name"],
            "smoothed": smoothed, "control": control,
            "raw_points": cd["points"], "length": cd["length"],
            "endpoint": cd["endpoint"], "angle": cd["angle"],
        })
        print(f"  [{cd['key']}] {cd['name']}: {len(cd['points'])} raw → {len(control)} RDP → {len(smoothed)} smooth")

    # 5. 导出
    print("\n[5/5] Exporting...")
    os.makedirs(output_dir, exist_ok=True)
    image_size = (w, h)

    if "svg" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}.svg")
        export_svg(curves_data, image_size, path, stroke_width=args.stroke_width,
                   show_control_points=args.show_control_points)
        print(f"  SVG: {path}")

    if "json" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}.json")
        export_json(curves_data, path, version=args.version)
        print(f"  JSON: {path}")

    if "csv" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}.csv")
        export_csv(curves_data, path)
        print(f"  CSV: {output_dir}/{name_prefix}_*.csv (one per curve)")

    if "dxf" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}.dxf")
        export_dxf(curves_data, path)
        print(f"  DXF: {path}")

    if "obj" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}.obj")
        export_obj(curves_data, path)
        print(f"  OBJ: {path}")

    if "ue_spline" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}_ue_spline.json")
        export_ue_spline(curves_data, path, world_scale=args.world_scale)
        print(f"  UE Spline: {path}")

    if "niagara" in args.export:
        path = os.path.join(output_dir, f"{name_prefix}_niagara.csv")
        export_niagara_path(curves_data, path, world_scale=args.world_scale)
        print(f"  Niagara: {path}")

    if "ue_script" in args.export:
        spline_path = os.path.join(output_dir, f"{name_prefix}_ue_spline.json")
        if "ue_spline" not in args.export:
            export_ue_spline(curves_data, spline_path, world_scale=args.world_scale)
        script_path = os.path.join(output_dir, f"{name_prefix}_ue_import.py")
        generate_ue_import_script(spline_path, script_path, actor_name=f"CurveExtractor_{name_prefix}")
        print(f"  UE Import Script: {script_path}")

    # 可视化
    if args.save_intermediate:
        from src.trace_angle import define_root_region, multi_source_bfs
        root_mask = define_root_region(skeleton_pruned, y_ratio=args.root_y_ratio)
        root_pixels = list(zip(*np.where(root_mask)))
        dist = multi_source_bfs(skeleton_pruned, root_pixels)
        save_intermediate_results(rgb, solid, skeleton_pruned, dist, output_dir, name_prefix)

    if args.comparison:
        path = os.path.join(output_dir, f"{name_prefix}_comparison.png")
        make_comparison_figure(curves_data, rgb, path)
        print(f"  Comparison: {path}")

    # 质量评估
    if args.quality_report:
        report = evaluate_all_curves(curves_data)
        print_quality_report(report)
        report_path = os.path.join(output_dir, f"{name_prefix}_quality_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Quality report: {report_path}")

    print(f"\n✓ Done! Output saved to: {output_dir}")
    return curves_data


def main():
    args = parse_args()

    # 收集输入文件
    input_files = []
    if args.batch:
        for pattern in args.batch:
            input_files.extend(glob.glob(pattern))
    elif args.input:
        input_files = [args.input]
    else:
        # 默认使用 input/original.png
        default_input = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "input", "original.png")
        if os.path.exists(default_input):
            input_files = [default_input]
        else:
            print("Error: No input file specified. Use -i or --batch.")
            sys.exit(1)

    if not input_files:
        print("Error: No input files found.")
        sys.exit(1)

    print(f"Curve Extractor {args.version}")
    print(f"Input files: {len(input_files)}")
    print(f"Output directory: {args.output}")
    print(f"Export formats: {', '.join(args.export)}")

    for input_path in input_files:
        if not os.path.exists(input_path):
            print(f"Warning: File not found: {input_path}")
            continue
        name_prefix = os.path.splitext(os.path.basename(input_path))[0]
        # 批量处理时每个文件一个子目录
        out_dir = args.output if len(input_files) == 1 else os.path.join(args.output, name_prefix)
        process_single_image(input_path, out_dir, args, name_prefix)

    print(f"\n{'='*60}")
    print(f"All done! Processed {len(input_files)} file(s).")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
