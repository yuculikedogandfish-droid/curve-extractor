# Curve Extractor — Blender add-on (standalone, internal distribution)
# Extract curves from a local image, or import JSON. Do not publish.

bl_info = {
    "name": "Curve Extractor",
    "author": "Internal FX",
    "version": (1, 4, 26),
    "blender": (3, 3, 0),
    "location": "View3D > Sidebar > Curve Extractor",
    "description": "从本地图片提取曲线并生成交叉面片（内部分发）",
    "category": "Object",
}

import os
import sys

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if _ADDON_DIR not in sys.path:
    sys.path.insert(0, _ADDON_DIR)

import bpy
from bpy.props import (
    StringProperty, FloatProperty, IntProperty, BoolProperty, EnumProperty,
)
from bpy_extras.io_utils import ImportHelper, ExportHelper
from mathutils import Vector

from . import core


def _safe_name(name):
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))
    return (cleaned or "Curve")[:60]


def _world_to_blender(x, y, z, z_up=True):
    if z_up:
        return Vector(core.html_world_to_zup(x, y, z))
    return Vector(core.html_world_to_yup(x, y, z))


def _poly_curve(name, points, scale=0.01):
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 2
    spline = curve_data.splines.new("POLY")
    spline.points.add(max(0, len(points) - 1))
    for i, p in enumerate(points):
        spline.points[i].co = (p.x * scale, p.y * scale, p.z * scale, 1.0)
    return bpy.data.objects.new(name, curve_data)


def _mesh_from_sheet(name, verts, faces, uvs):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name="UVMap")
    loop_i = 0
    for face in faces:
        for vi in face:
            uv.data[loop_i].uv = uvs[vi]
            loop_i += 1
    return bpy.data.objects.new(name, mesh)


def _params_from_scene(props):
    return core.ExtractParams(
        bright_thresh=props.bright_thresh,
        hue_min=props.hue_min,
        hue_max=props.hue_max,
        sat_min=props.sat_min,
        branch_detail=props.branch_detail,
        branch_attach=props.branch_attach,
        growth_axis=props.growth_axis,
        min_length=props.min_length,
    )


def _card_from_scene(props):
    return core.CardParams(
        count=props.card_count,
        width=props.card_width,
        taper=props.taper,
        cross_angle=props.cross_angle,
    )


def _build_collection(context, name="CurveExtractor"):
    col = bpy.data.collections.new(name)
    context.scene.collection.children.link(col)
    return col


def _spawn_result(context, result, scale, z_up, make_curves, make_cards, col_name="CurveExtractor"):
    card = result.card
    col = _build_collection(context, col_name)
    created_c = created_m = 0
    for i, entry in enumerate(result.curves):
        pts = [_world_to_blender(*xyz, z_up=z_up) for xyz in entry.points3d]
        if len(pts) < 2:
            continue
        name = _safe_name(entry.name or entry.key or "Curve_%02d" % (i + 1))
        if make_curves:
            obj = _poly_curve(name, pts, scale=scale)
            col.objects.link(obj)
            created_c += 1
        if make_cards:
            sheets = core.build_card_sheets(entry.points3d, card, scale=scale)
            for k, (verts, faces, uvs) in enumerate(sheets):
                bverts = []
                for vx, vy, vz in verts:
                    bp = _world_to_blender(vx / scale, vy / scale, vz / scale, z_up=z_up)
                    bverts.append((bp.x * scale, bp.y * scale, bp.z * scale))
                obj = _mesh_from_sheet("%s_card%d" % (name, k + 1), bverts, faces, uvs)
                col.objects.link(obj)
                created_m += 1
    return created_c, created_m


def _pixels_from_blender_image(img):
    import numpy as np

    w, h = img.size[0], img.size[1]
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, img.channels)
    rgb = px[..., :3]
    # Blender pixels are bottom-up
    rgb = rgb[::-1]
    return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)


class CURVEEXT_OT_extract_image(bpy.types.Operator, ImportHelper):
    bl_idname = "curve_extractor.extract_image"
    bl_label = "从图片提取曲线"
    bl_description = "本地加载光效/线稿图，在 Blender 内提取曲线和交叉面片"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ""
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.bmp", options={"HIDDEN"})

    def execute(self, context):
        props = context.scene.curve_extractor
        path = self.filepath
        try:
            img = bpy.data.images.load(path, check_existing=True)
            rgb = _pixels_from_blender_image(img)
        except Exception as e:
            self.report({"ERROR"}, "读图失败: %s" % e)
            return {"CANCELLED"}
        try:
            result = core.extract_from_rgb(rgb, _params_from_scene(props), _card_from_scene(props))
        except Exception as e:
            self.report({"ERROR"}, "提取失败: %s" % e)
            return {"CANCELLED"}
        if not result.curves:
            self.report({"WARNING"}, "没有提出曲线。可调亮度阈值或枝条精细度后重试")
            return {"CANCELLED"}
        c, m = _spawn_result(
            context, result, props.scale, props.z_up, True, props.make_cards,
            col_name="CurveExtractor",
        )
        kind = "线稿" if result.line_drawing else "光效"
        self.report({"INFO"}, "提取 %s：%d 条曲线、%d 张面片" % (kind, c, m))
        return {"FINISHED"}


class CURVEEXT_OT_import_json(bpy.types.Operator, ImportHelper):
    bl_idname = "curve_extractor.import_json"
    bl_label = "导入 JSON"
    bl_description = "导入本插件或内部工具导出的 curves.json"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        props = context.scene.curve_extractor
        try:
            result = core.load_json_file(self.filepath)
        except Exception as e:
            self.report({"ERROR"}, "无法读取 JSON: %s" % e)
            return {"CANCELLED"}
        if not result.curves:
            self.report({"ERROR"}, "JSON 里没有曲线")
            return {"CANCELLED"}
        if result.card.count == 2 and props.card_count != 2:
            result.card = _card_from_scene(props)
        c, m = _spawn_result(context, result, props.scale, props.z_up, True, props.make_cards)
        self.report({"INFO"}, "导入 %d 条曲线、%d 张面片" % (c, m))
        return {"FINISHED"}


class CURVEEXT_OT_export_json(bpy.types.Operator, ExportHelper):
    bl_idname = "curve_extractor.export_json"
    bl_label = "导出选中曲线为 JSON"
    bl_options = {"REGISTER"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        props = context.scene.curve_extractor
        sel = [o for o in context.selected_objects if o.type == "CURVE"]
        if not sel:
            self.report({"ERROR"}, "请先选中曲线")
            return {"CANCELLED"}
        result = core.ExtractResult(card=_card_from_scene(props))
        for i, obj in enumerate(sel):
            pts = []
            for spline in obj.data.splines:
                for p in spline.points:
                    v = obj.matrix_world @ Vector(p.co.xyz)
                    if props.z_up:
                        # inverse of (x,z,-y): x=x, y=-z, z=y
                        pts.append([v.x / props.scale, -v.z / props.scale, v.y / props.scale])
                    else:
                        pts.append([v.x / props.scale, -v.y / props.scale, v.z / props.scale])
            if len(pts) < 2:
                continue
            import numpy as np
            world = np.asarray(pts, dtype=np.float64)
            result.curves.append(
                core.ExtractedCurve(
                    key="curve_%02d" % (i + 1),
                    name=obj.name,
                    points_yx=world[:, :2],
                    points3d=world,
                    level=1,
                    color_rgb=(255, 215, 0),
                )
            )
        if not result.curves:
            self.report({"ERROR"}, "选中曲线没有可用点")
            return {"CANCELLED"}
        core.save_json_file(result, self.filepath)
        self.report({"INFO"}, "已导出 %d 条" % len(result.curves))
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
        card = _card_from_scene(props)
        nmesh = 0
        for obj in sel:
            pts = []
            for spline in obj.data.splines:
                for p in spline.points:
                    pts.append(tuple(p.co.xyz))
                for p in spline.bezier_points:
                    pts.append(tuple(p.co))
            if len(pts) < 2:
                continue
            import numpy as np
            sheets = core.build_card_sheets(
                np.asarray(pts, dtype=np.float64),
                core.CardParams(card.count, card.width * props.scale, card.taper, card.cross_angle),
                scale=1.0,
            )
            for k, (verts, faces, uvs) in enumerate(sheets):
                m = _mesh_from_sheet("%s_card%d" % (obj.name, k + 1), verts, faces, uvs)
                col = obj.users_collection[0] if obj.users_collection else context.collection
                col.objects.link(m)
                nmesh += 1
        self.report({"INFO"}, "生成 %d 张面片" % nmesh)
        return {"FINISHED"}


class CURVEEXT_Props(bpy.types.PropertyGroup):
    scale: FloatProperty(name="像素缩放", default=0.01, min=0.0001, max=10.0,
                         description="约 1024 像素 = 10.24 米")
    z_up: BoolProperty(name="Blender Z-up", default=True)
    make_cards: BoolProperty(name="同时生成面片", default=True)
    card_count: IntProperty(name="面片数量", default=2, min=1, max=4)
    card_width: FloatProperty(name="面片半宽(像素)", default=24.0, min=1.0, max=200.0)
    taper: FloatProperty(name="尖端收窄", default=0.15, min=0.0, max=1.0)
    cross_angle: FloatProperty(name="两片夹角", default=90.0, min=10.0, max=180.0)
    bright_thresh: FloatProperty(name="亮度阈值", default=0.70, min=0.15, max=1.0)
    hue_min: FloatProperty(name="色相最小", default=0.05, min=0.0, max=0.5)
    hue_max: FloatProperty(name="色相最大", default=0.17, min=0.0, max=0.5)
    sat_min: FloatProperty(name="饱和度下限", default=0.25, min=0.0, max=1.0)
    branch_detail: FloatProperty(name="枝条精细度", default=40.0, min=0.0, max=100.0)
    branch_attach: FloatProperty(name="分叉着生", default=70.0, min=0.0, max=100.0)
    growth_axis: FloatProperty(name="走势轴向", default=50.0, min=0.0, max=100.0,
                               description="左=横向连续，右=竖向根系，中=按长宽自动")
    min_length: IntProperty(name="最短曲线", default=30, min=10, max=300)


class CURVEEXT_PT_panel(bpy.types.Panel):
    bl_label = "Curve Extractor"
    bl_idname = "CURVEEXT_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Curve Extractor"

    def draw(self, context):
        layout = self.layout
        props = context.scene.curve_extractor
        box = layout.box()
        box.label(text="内部工具 · 勿外传")
        layout.operator("curve_extractor.extract_image", icon="IMAGE_DATA")
        layout.operator("curve_extractor.import_json", icon="IMPORT")
        layout.operator("curve_extractor.export_json", icon="EXPORT")
        layout.separator()
        layout.label(text="提取")
        layout.prop(props, "bright_thresh")
        layout.prop(props, "branch_detail")
        layout.prop(props, "branch_attach")
        layout.prop(props, "growth_axis")
        layout.separator()
        layout.label(text="场景 / 面片")
        layout.prop(props, "scale")
        layout.prop(props, "z_up")
        layout.prop(props, "make_cards")
        layout.prop(props, "card_count")
        layout.prop(props, "card_width")
        layout.prop(props, "taper")
        layout.prop(props, "cross_angle")
        layout.operator("curve_extractor.cards_from_selected", icon="MESH_PLANE")


classes = (
    CURVEEXT_Props,
    CURVEEXT_OT_extract_image,
    CURVEEXT_OT_import_json,
    CURVEEXT_OT_export_json,
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
