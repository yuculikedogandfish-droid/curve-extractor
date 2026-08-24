"""
多格式导出模块：SVG / JSON / CSV / DXF / OBJ / UE Spline / Niagara 路径 / UE Python 导入脚本
"""
import json
import os
import numpy as np


CURVE_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]


# ============================================================
# SVG 导出
# ============================================================
def export_svg(curves_data: list, image_size: tuple, output_path: str,
               stroke_width: float = 3.0, show_control_points: bool = False):
    """导出 SVG 矢量曲线。"""
    w, h = image_size
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '  <rect width="100%" height="100%" fill="black"/>',
    ]
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        color = CURVE_COLORS[i % len(CURVE_COLORS)]
        d = f"M {pts[0,1]:.1f} {pts[0,0]:.1f}"
        for p in pts[1:]:
            d += f" L {p[1]:.1f} {p[0]:.1f}"
        parts.append(
            f'  <path d="{d}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" '
            f'id="{cd["key"]}" name="{cd["name"]}"/>'
        )
        if show_control_points and "control" in cd:
            ctrl = cd["control"]
            for cp in ctrl:
                parts.append(
                    f'  <circle cx="{cp[1]:.1f}" cy="{cp[0]:.1f}" r="4" '
                    f'fill="{color}" stroke="white" stroke-width="1"/>'
                )
    parts.append("</svg>")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


# ============================================================
# JSON 导出
# ============================================================
def export_json(curves_data: list, output_path: str, version: str = "v0.8"):
    """导出 JSON 曲线数据（含 RDP 拐点、弧长、角度等元数据）。"""
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


# ============================================================
# CSV 导出
# ============================================================
def export_csv(curves_data: list, output_path: str):
    """导出 CSV：每根曲线一个文件，列为 point_index, x, y, arc_length。"""
    base, ext = os.path.splitext(output_path)
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        lengths = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
        cum_len = np.concatenate([[0], np.cumsum(lengths)])
        fname = f"{base}_{cd['key']}.csv"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("point_index,x,y,arc_length_px\n")
            for j, p in enumerate(pts):
                f.write(f"{j},{p[1]:.3f},{p[0]:.3f},{cum_len[j]:.3f}\n")


# ============================================================
# DXF 导出（CAD 软件可用）
# ============================================================
def export_dxf(curves_data: list, output_path: str, scale: float = 1.0):
    """导出 DXF 多段线（POLYLINE），CAD 软件（AutoCAD/Illustrator）可直接打开。"""
    lines = [
        "0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009",
        "0", "ENDSEC", "0", "SECTION", "2", "TABLES",
        "0", "TABLE", "2", "LAYER", "70", str(len(curves_data)),
    ]
    for i, cd in enumerate(curves_data):
        color = (i + 1) % 256
        lines += ["0", "LAYER", "2", cd["key"], "70", "0", "62", str(color), "6", "CONTINUOUS"]
    lines += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]

    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        n = len(pts)
        lines += [
            "0", "POLYLINE", "8", cd["key"], "66", "1", "70", "0",
            "10", "0.0", "20", "0.0", "30", "0.0",
        ]
        for p in pts:
            x = p[1] * scale
            y = -p[0] * scale  # DXF Y 轴向上，图像 Y 轴向下
            lines += ["0", "VERTEX", "8", cd["key"], "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0.0"]
        lines += ["0", "SEQEND", "8", cd["key"]]

    lines += ["0", "ENDSEC", "0", "EOF"]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# OBJ 导出（3D 软件可用，曲线作为线段）
# ============================================================
def export_obj(curves_data: list, output_path: str, z_spread: float = 0.0):
    """导出 OBJ：每根曲线作为一组线段，可在 Blender/Maya/UE 中导入。"""
    verts = []
    faces = []
    v_offset = 1
    for i, cd in enumerate(curves_data):
        pts = cd["smoothed"]
        z = (i - len(curves_data) / 2) * z_spread
        for p in pts:
            verts.append(f"v {p[1]:.3f} {-p[0]:.3f} {z:.3f}")
        for j in range(len(pts) - 1):
            faces.append(f"l {v_offset + j} {v_offset + j + 1}")
        v_offset += len(pts)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# Curve Extractor OBJ export\n# {len(curves_data)} curves\n\n")
        f.write("\n".join(verts) + "\n\n")
        f.write("\n".join(faces) + "\n")


# ============================================================
# UE Spline 数据导出（JSON，UE 中用 Python 脚本读取生成 SplineComponent）
# ============================================================
def export_ue_spline(curves_data: list, output_path: str,
                      world_scale: float = 0.1, z_height: float = 0.0):
    """
    导出 UE Spline 数据（JSON 格式）。
    每根曲线包含：名称、关键点（世界坐标）、切线类型。
    UE 中可用 Python 脚本读取，生成 SplineComponent。
    """
    data = {"type": "UE_SplineData", "curve_count": len(curves_data), "world_scale": world_scale, "curves": []}
    for cd in curves_data:
        pts = cd["smoothed"]
        # 每 20 个点取一个关键点（UE Spline 不需要 800 个点）
        step = max(1, len(pts) // 40)
        key_points = []
        for j in range(0, len(pts), step):
            p = pts[j]
            key_points.append({
                "location": [round(p[1] * world_scale, 3), round(-p[0] * world_scale, 3), z_height],
                "tangent_mode": "Auto",
            })
        # 确保最后一个点包含
        if len(pts) - 1 not in range(0, len(pts), step):
            p = pts[-1]
            key_points.append({
                "location": [round(p[1] * world_scale, 3), round(-p[0] * world_scale, 3), z_height],
                "tangent_mode": "Auto",
            })
        data["curves"].append({
            "key": cd["key"], "name": cd["name"],
            "spline_points": key_points, "point_count": len(key_points),
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# Niagara 粒子路径导出（CSV，UE Niagara 可直接读取）
# ============================================================
def export_niagara_path(curves_data: list, output_path: str,
                         world_scale: float = 0.1, samples_per_curve: int = 100):
    """
    导出 Niagara 粒子路径数据（CSV）。
    格式：CurveID, PointID, Position.X, Position.Y, Position.Z, Tangent.X, Tangent.Y, Tangent.Z
    UE Niagara 中可作为粒子位置数据使用。
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("CurveID,PointID,PosX,PosY,PosZ,TanX,TanY,TanZ\n")
        for i, cd in enumerate(curves_data):
            pts = cd["smoothed"]
            # 重采样到指定点数
            t = np.linspace(0, 1, len(pts))
            t_new = np.linspace(0, 1, samples_per_curve)
            y_interp = np.interp(t_new, t, pts[:, 0])
            x_interp = np.interp(t_new, t, pts[:, 1])
            for j in range(samples_per_curve):
                px = x_interp[j] * world_scale
                py = -y_interp[j] * world_scale
                pz = 0.0
                # 计算切线
                if j < samples_per_curve - 1:
                    tx = (x_interp[j+1] - x_interp[j]) * world_scale
                    ty = -(y_interp[j+1] - y_interp[j]) * world_scale
                else:
                    tx = (x_interp[j] - x_interp[j-1]) * world_scale
                    ty = -(y_interp[j] - y_interp[j-1]) * world_scale
                norm = np.sqrt(tx*tx + ty*ty) + 1e-6
                f.write(f"{i},{j},{px:.4f},{py:.4f},{pz:.4f},{tx/norm:.4f},{ty/norm:.4f},0.0\n")


# ============================================================
# UE Python 导入脚本生成
# ============================================================
def generate_ue_import_script(spline_json_path: str, output_path: str,
                               actor_name: str = "CurveExtractorActor"):
    """
    生成 UE Python 导入脚本。
    在 UE 中运行此脚本，读取 spline JSON 数据，在场景中生成带 SplineComponent 的 Actor。
    """
    script = f'''# UE Python 导入脚本 — 由 Curve Extractor 生成
# 在 UE 编辑器中运行：窗口 -> 开发者工具 -> Python 脚本，或用 py 命令执行
import json
import unreal

# 读取 Spline 数据
with open(r"{spline_json_path.replace(chr(92), chr(47))}", "r", encoding="utf-8") as f:
    data = json.load(f)

world = unreal.EditorLevelLibrary.get_editor_world()

# 创建 Actor
actor_class = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(0, 0, 0)
)
actor.set_actor_label("{actor_name}")

for curve_data in data["curves"]:
    # 创建 SplineComponent
    spline_comp = unreal.SplineComponent()
    spline_comp.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    actor.add_component(spline_comp, unreal.Name(curve_data["key"]))

    # 设置 Spline 点
    points = curve_data["spline_points"]
    spline_comp.clear_spline_points()
    for i, pt in enumerate(points):
        loc = unreal.Vector(pt["location"][0], pt["location"][1], pt["location"][2])
        spline_comp.add_spline_point_at_index(loc, i, unreal.SplineCoordinateSpace.WORLD)

    spline_comp.update_spline()
    print(f"  Created spline: {{curve_data['name']}} ({{curve_data['point_count']}} points)")

print(f"\\nImport complete: {{data['curve_count']}} curves imported to {{actor_name}}")
'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script)
