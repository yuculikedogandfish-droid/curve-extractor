"""
智能曲线追踪测试脚本
处理复杂光效图，自动提取所有曲线
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import numpy as np
from PIL import Image
from src.preprocess import extract_golden_mask, solidify_mask, skeletonize, prune_skeleton
from src.trace_smart import trace_all_curves_smart, trace_all_curves_by_components
from src.smooth import smooth_trend_curve
from src.export import export_svg, export_json

# 配置
INPUT_PATH = r"H:\tool\curve-extractor\input\complex_test.png"
OUTPUT_DIR = r"H:\tool\curve-extractor\output\smart_test"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 参数
CLOSE_RADIUS = 5
DILATE_RADIUS = 1
MIN_OBJECT_SIZE = 200
PRUNE_LENGTH = 20
MIN_CURVE_LENGTH = 80
RDP_EPSILON = 3.0
NUM_SAMPLES = 300

print("=" * 60)
print("智能曲线追踪测试")
print("=" * 60)

# 1. 读取图片
print(f"\n[1/6] 读取图片: {INPUT_PATH}")
img = Image.open(INPUT_PATH).convert('RGB')
w, h = img.size
print(f"  尺寸: {w}x{h}")
rgb = np.array(img)

# 2. HSV掩码
print("\n[2/6] HSV金色掩码提取...")
mask = extract_golden_mask(rgb)
print(f"  掩码像素数: {mask.sum()}")

# 3. 形态学固化
print("\n[3/6] 形态学固化...")
solid = solidify_mask(mask, close_radius=CLOSE_RADIUS,
                      dilate_radius=DILATE_RADIUS,
                      min_object_size=MIN_OBJECT_SIZE)
print(f"  固化后像素数: {solid.sum()}")

# 4. 骨架化
print("\n[4/6] 骨架化 + 修剪...")
skel = skeletonize(solid)
skel_pruned = prune_skeleton(skel, min_branch_length=PRUNE_LENGTH)
print(f"  骨架像素数: {skel_pruned.sum()}")

# 转换为一维数组（trace_smart 使用一维索引）
skel_1d = skel_pruned.flatten()

# 5. 智能追踪
print("\n[5/6] 智能曲线追踪...")
# 方法1: 端点对追踪
curves_smart = trace_all_curves_smart(skel_1d, w, h,
                                         min_length=MIN_CURVE_LENGTH,
                                         max_curves=50)

# 方法2: 连通分量追踪
curves_comp = trace_all_curves_by_components(skel_1d, w, h,
                                               min_length=MIN_CURVE_LENGTH)

# 选择曲线数量更多的方法
if len(curves_smart) >= len(curves_comp):
    curves = curves_smart
    method = "端点对追踪"
else:
    curves = curves_comp
    method = "连通分量追踪"

print(f"\n  使用方法: {method}")
print(f"  最终提取曲线数: {len(curves)}")
for i, c in enumerate(curves[:10]):
    print(f"    曲线{i+1}: {len(c)} 点")

# 6. 简化 + 平滑
print("\n[6/6] RDP简化 + B样条插值...")
smoothed_curves = []
curves_data = []  # 用于导出的格式
for i, curve in enumerate(curves):
    # 转换为 numpy 数组 (N, 2)，列为 [y, x]
    pts_arr = np.array(curve)  # curve 是 [(y,x), ...]
    # smooth_trend_curve 返回 (smoothed, control_points)
    smoothed, control = smooth_trend_curve(pts_arr, num_samples=NUM_SAMPLES,
                                             rdp_epsilon=RDP_EPSILON)
    smoothed_curves.append(smoothed)

    # 计算角度（起点到终点）
    start_y, start_x = curve[0]
    end_y, end_x = curve[-1]
    angle = np.degrees(np.arctan2(end_y - start_y, end_x - start_x))

    curves_data.append({
        "key": f"curve_{i+1}",
        "name": f"Curve {i+1}",
        "smoothed": smoothed,
        "control": control,
        "length": len(curve),
        "endpoint": np.array([end_y, end_x]),
        "angle": angle,
    })
    print(f"  曲线{i+1}: {len(curve)}→{len(control)}拐点→{len(smoothed)}采样点, 角度={angle:.1f}°")

# 导出
print("\n导出结果...")
base_name = os.path.splitext(os.path.basename(INPUT_PATH))[0]

# SVG
svg_path = os.path.join(OUTPUT_DIR, f"{base_name}.svg")
export_svg(curves_data, (w, h), svg_path)
print(f"  SVG: {svg_path}")

# JSON
json_path = os.path.join(OUTPUT_DIR, f"{base_name}.json")
export_json(curves_data, json_path)
print(f"  JSON: {json_path}")

# 生成预览图（叠加曲线）
print("\n生成预览图...")
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 3, figsize=(24, 8))

# 原图
axes[0].imshow(rgb)
axes[0].set_title('Original', fontsize=14)
axes[0].axis('off')

# 骨架
skel_img = np.zeros((h, w, 3), dtype=np.uint8)
skel_img[skel_pruned > 0] = [255, 255, 255]
axes[1].imshow(skel_img)
axes[1].set_title(f'Skeleton ({len(curves)} curves detected)', fontsize=14)
axes[1].axis('off')

# 曲线叠加
axes[2].imshow(rgb, alpha=0.3)
colors = plt.cm.tab20(np.linspace(0, 1, len(smoothed_curves)))
for i, curve in enumerate(smoothed_curves):
    ys = curve[:, 0]
    xs = curve[:, 1]
    axes[2].plot(xs, ys, color=colors[i], linewidth=2, label=f'Curve {i+1}')
axes[2].set_title(f'Extracted Curves ({len(smoothed_curves)})', fontsize=14)
axes[2].axis('off')
if len(smoothed_curves) <= 15:
    axes[2].legend(loc='upper right', fontsize=8)

plt.tight_layout()
preview_path = os.path.join(OUTPUT_DIR, f"{base_name}_preview.png")
plt.savefig(preview_path, dpi=100, bbox_inches='tight')
plt.close()
print(f"  预览图: {preview_path}")

print("\n" + "=" * 60)
print("完成!")
print("=" * 60)
