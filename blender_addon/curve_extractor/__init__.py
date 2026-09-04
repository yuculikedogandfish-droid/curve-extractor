# Curve Extractor — Blender add-on
# Import 3D curves + crossing cards from the HTML tool's JSON (v1.4.19+).

bl_info = {
    "name": "Curve Extractor",
    "author": "Curve Extractor",
    "version": (1, 4, 22),
    "blender": (3, 3, 0),
    "location": "View3D > Sidebar > Curve Extractor",
    "description": "从 Curve Extractor JSON 导入 3D 曲线并生成交叉面片",
    "category": "Import-Export",
    "doc_url": "https://github.com/yuculikedogandfish-droid/curve-extractor",
}

import math
import json
import bpy
from bpy.props import (
    StringProperty, FloatProperty, IntProperty, BoolProperty,
)
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector


def safe_name(name):
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))
    return (cleaned or "Curve")[:60]


def html_world_to_blender(x, y, z, z_up=True):
    """HTML world: x right, y image-down, z forward.
    OBJ/UE Y-up: (x, -y, z). Blender Z-up: (x, z, -y).
    """
    if z_up:
        return Vector((x, z, -y))
    return Vector((x, -y, z))


def poly_to_curve(name, points, scale=0.01):
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 2
    spline = curve_data.splines.new("POLY")
    spline.points.add(max(0, len(points) - 1))
    for i, p in enumerate(points):
        spline.points[i].co = (p.x * scale, p.y * scale, p.z * scale, 1.0)
    return bpy.data.objects.new(name, curve_data)


def frames_along(points):
    n = len(points)
    T = []
    for i in range(n):
        a = points[max(0, i - 1)]
        b = points[min(n - 1, i + 1)]
        t = b - a
        if t.length < 1e-8:
            t = Vector((0, 0, 1))
        else:
            t.normalize()
        T.append(t)
    n0 = T[0].cross(Vector((0, 0, 1)))
    if n0.length < 1e-4:
        n0 = T[0].cross(Vector((1, 0, 0)))
    n0.normalize()
    N = [n0]
    for i in range(1, n):
        prev = N[i - 1]
        d = prev.dot(T[i])
        ni = prev - T[i] * d
        if ni.length < 1e-6:
            axis = T[i - 1].cross(T[i])
            if axis.length < 1e-6:
                ni = prev
            else:
                axis.normalize()
                ni = axis.cross(T[i])
                ni.normalize()
        else:
            ni.normalize()
        N.append(ni)
    B = [T[i].cross(N[i]).normalized() for i in range(n)]
    return T, N, B


def build_cards(name, points, count=2, width=24.0, taper=0.15, cross_angle=90.0,
                pos_scale=0.01, width_scale=None):
    """pos_scale 乘在曲线点上。导入 JSON 时点和半宽都是像素，两者同用 0.01。
    从已导入曲线重生成时点已是场景单位，pos_scale=1，半宽仍按像素 × width_scale。
    """
    if width_scale is None:
        width_scale = pos_scale
    n = len(points)
    if n < 2:
        return []
    _, Nrm, Bin = frames_along(points)
    cross_rad = math.radians(cross_angle)
    objs = []
    for k in range(max(1, count)):
        if count == 1:
            angle = 0.0
        elif count == 2:
            angle = -cross_rad / 2 + k * cross_rad
        else:
            angle = k * math.pi / count
        ca, sa = math.cos(angle), math.sin(angle)
        verts = []
        uvs = []
        for i, p in enumerate(points):
            t = i / max(1, n - 1)
            dx = Nrm[i] * ca + Bin[i] * sa
            w = width * (1.0 - taper * t) * width_scale
            left = p * pos_scale - dx * w
            right = p * pos_scale + dx * w
            verts.extend([(left.x, left.y, left.z), (right.x, right.y, right.z)])
            uvs.extend([(0.0, t), (1.0, t)])
        faces = []
        for i in range(n - 1):
            a, b, c, d = i * 2, i * 2 + 1, (i + 1) * 2, (i + 1) * 2 + 1
            faces.append((a, b, d, c))
        mesh = bpy.data.meshes.new(f"{name}_card{k + 1}")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        uv = mesh.uv_layers.new(name="UVMap")
        loop_i = 0
        for face in faces:
            for vi in face:
                uv.data[loop_i].uv = uvs[vi]
                loop_i += 1
        objs.append(bpy.data.objects.new(f"{name}_card{k + 1}", mesh))
    return objs


def parse_curve_points(entry, z_up=True):
    if entry.get("points3d"):
        pts = []
        for x, y, z in entry["points3d"]:
            pts.append(html_world_to_blender(x, y, z, z_up=z_up))
        return pts
    if entry.get("points3d_yup"):
        pts = []
        for x, y, z in entry["points3d_yup"]:
            if z_up:
                pts.append(Vector((x, z, y)))
            else:
                pts.append(Vector((x, y, z)))
        return pts
    raw = entry.get("points") or []
    pts = []
    for item in raw:
        if len(item) >= 2:
            x, y = float(item[0]), float(item[1])
            pts.append(html_world_to_blender(x, y, 0.0, z_up=z_up))
    return pts


class CURVEEXT_OT_import_json(bpy.types.Operator, ImportHelper):
    bl_idname = "curve_extractor.import_json"
    bl_label = "导入 Curve Extractor JSON"
    bl_description = "导入 HTML 工具导出的 curves.json，生成 3D 曲线和交叉面片"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    scale: FloatProperty(name="缩放", default=0.01, min=0.0001, max=10.0,
                         description="像素→场景单位。0.01 时约 1024px = 10.24m")
    z_up: BoolProperty(name="Blender Z-up", default=True,
                       description="勾选：转成 Blender 默认 Z 向上。取消：与 OBJ/UE 的 Y-up 一致")
    make_cards: BoolProperty(name="生成交叉面片", default=True)
    make_curves: BoolProperty(name="生成曲线", default=True)

    def execute(self, context):
        props = context.scene.curve_extractor
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.report({"ERROR"}, f"无法读取 JSON: {e}")
            return {"CANCELLED"}
        curves = data.get("curves") or []
        if not curves:
            self.report({"ERROR"}, "JSON 里没有 curves")
            return {"CANCELLED"}
        card = data.get("card") or {}
        count = int(card.get("count", props.card_count))
        width = float(card.get("width", props.card_width))
        taper = float(card.get("taper", props.taper))
        angle = float(card.get("crossAngle", props.cross_angle))
        col = bpy.data.collections.new("CurveExtractor")
        context.scene.collection.children.link(col)
        created_c, created_m = 0, 0
        for i, entry in enumerate(curves):
            pts = parse_curve_points(entry, z_up=self.z_up)
            if len(pts) < 2:
                continue
            name = safe_name(entry.get("name") or entry.get("key") or f"Curve_{i + 1:02d}")
            if self.make_curves:
                obj = poly_to_curve(name, pts, scale=self.scale)
                col.objects.link(obj)
                created_c += 1
            if self.make_cards:
                meshes = build_cards(
                    name, pts, count=count, width=width, taper=taper,
                    cross_angle=angle, pos_scale=self.scale,
                )
                for m in meshes:
                    col.objects.link(m)
                    created_m += 1
        self.report({"INFO"}, f"导入 {created_c} 条曲线、{created_m} 张面片")
        return {"FINISHED"}


class CURVEEXT_OT_cards_from_selected(bpy.types.Operator):
    bl_idname = "curve_extractor.cards_from_selected"
    bl_label = "从选中曲线生成面片"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.curve_extractor
        sel = [o for o in context.selected_objects if o.type == "CURVE"]
        if not sel:
            self.report({"ERROR"}, "请先选中曲线物体")
            return {"CANCELLED"}
        nmesh = 0
        for obj in sel:
            pts = []
            for spline in obj.data.splines:
                for p in spline.points:
                    pts.append(Vector(p.co.xyz))
                for p in spline.bezier_points:
                    pts.append(Vector(p.co))
            if len(pts) < 2:
                continue
            meshes = build_cards(
                obj.name, pts,
                count=props.card_count, width=props.card_width,
                taper=props.taper, cross_angle=props.cross_angle,
                pos_scale=1.0, width_scale=props.scale,
            )
            for m in meshes:
                col = obj.users_collection[0] if obj.users_collection else context.collection
                col.objects.link(m)
            nmesh += len(meshes)
        self.report({"INFO"}, f"生成 {nmesh} 张面片")
        return {"FINISHED"}


class CURVEEXT_Props(bpy.types.PropertyGroup):
    scale: FloatProperty(name="像素缩放", default=0.01, min=0.0001, max=10.0,
                         description="重生成面片时：半宽(像素)×此值。导入 JSON 时以文件对话框里的缩放为准")
    card_count: IntProperty(name="面片数量", default=2, min=1, max=4)
    card_width: FloatProperty(name="面片半宽(像素)", default=24.0, min=1.0, max=200.0)
    taper: FloatProperty(name="尖端收窄", default=0.15, min=0.0, max=1.0)
    cross_angle: FloatProperty(name="两片夹角", default=90.0, min=10.0, max=180.0)


class CURVEEXT_PT_panel(bpy.types.Panel):
    bl_label = "Curve Extractor"
    bl_idname = "CURVEEXT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Curve Extractor"

    def draw(self, context):
        layout = self.layout
        props = context.scene.curve_extractor
        layout.label(text="1. HTML 工具导出 JSON")
        layout.operator("curve_extractor.import_json", icon="IMPORT")
        layout.separator()
        layout.label(text="面片参数（导入后也可重生成）")
        layout.prop(props, "scale")
        layout.prop(props, "card_count")
        layout.prop(props, "card_width")
        layout.prop(props, "taper")
        layout.prop(props, "cross_angle")
        layout.operator("curve_extractor.cards_from_selected", icon="MESH_PLANE")
        layout.separator()
        box = layout.box()
        box.label(text="流程")
        box.label(text="浏览器打开 HTML → 提取曲线")
        box.label(text="导出 JSON → 本面板导入")
        box.label(text="UE 请用 HTML 里的面片 FBX")


classes = (
    CURVEEXT_Props,
    CURVEEXT_OT_import_json,
    CURVEEXT_OT_cards_from_selected,
    CURVEEXT_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.curve_extractor = bpy.props.PointerProperty(type=CURVEEXT_Props)


def unregister():
    del bpy.types.Scene.curve_extractor
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
