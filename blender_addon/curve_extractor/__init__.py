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

_LAST = {"result": None, "path": None}


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
    p = core.ExtractParams(
        bright_thresh=props.bright_thresh,
        hue_min=props.hue_min,
        hue_max=props.hue_max,
        sat_min=props.sat_min,
        branch_detail=props.branch_detail,
        branch_attach=props.branch_attach,
        growth_axis=props.growth_axis,
        min_length=props.min_length,
        bg_enabled=props.bg_enabled,
        bg_tol=props.bg_tol,
        auto_invert=props.auto_invert,
        trust_top=props.trust_top / 100.0,
        tri_rectify=props.tri_rectify,
    )
    if props.fine_mode:
        p = core.apply_fine_mode(p)
    return p


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
            _LAST["result"] = result
            _LAST["path"] = path
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


class CURVEEXT_OT_extract_tri(bpy.types.Operator, ImportHelper):
    bl_idname = "curve_extractor.extract_tri"
    bl_label = "三视图提取（先选正面图）"
    bl_description = "正面 + 侧栏里的侧面/顶面路径。与网页三视图同一套：校正、信顶面、正视为准"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ""
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp", options={"HIDDEN"})

    def execute(self, context):
        props = context.scene.curve_extractor
        try:
            front = core.load_rgb_u8(self.filepath)
            side = core.load_rgb_u8(props.side_path) if props.side_path else None
            top = core.load_rgb_u8(props.top_path) if props.top_path else None
            result = core.extract_from_rgb(
                front, _params_from_scene(props), _card_from_scene(props),
                side_rgb=side, top_rgb=top, trust_top=props.trust_top / 100.0,
                tri_rectify=props.tri_rectify,
            )
        except Exception as e:
            self.report({"ERROR"}, "三视图提取失败: %s" % e)
            return {"CANCELLED"}
        if not result.curves:
            self.report({"WARNING"}, "没有提出曲线")
            return {"CANCELLED"}
        _LAST["result"] = result
        _LAST["path"] = self.filepath
        c, m = _spawn_result(context, result, props.scale, props.z_up, True, props.make_cards)
        self.report({"INFO"}, "三视图 %d 条、%d 张面片（信顶面 %d%%）" % (c, m, int(props.trust_top)))
        return {"FINISHED"}


class CURVEEXT_OT_pick_stroke(bpy.types.Operator):
    bl_idname = "curve_extractor.pick_stroke"
    bl_label = "点选补一笔"
    bl_description = "与网页相同：在已提取结果上按像素坐标补一笔。可先在图像编辑器打开原图，光标即像素位置"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.curve_extractor
        result = _LAST.get("result")
        if result is None or not result.of_cache:
            self.report({"ERROR"}, "请先提取曲线")
            return {"CANCELLED"}
        x, y = props.pick_x, props.pick_y
        for area in context.screen.areas:
            if area.type == "IMAGE_EDITOR" and area.spaces.active.image:
                space = area.spaces.active
                if space.cursor_location is not None and space.image.size[0]:
                    x = float(space.cursor_location[0])
                    y = float(space.image.size[1] - space.cursor_location[1])
        try:
            core.pick_stroke(result, x, y)
        except Exception as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        _LAST["result"] = result
        c, m = _spawn_result(context, result, props.scale, props.z_up, True, props.make_cards)
        self.report({"INFO"}, "已补一笔，现在 %d 条" % c)
        return {"FINISHED"}


class CURVEEXT_OT_export_fbx(bpy.types.Operator, ExportHelper):
    bl_idname = "curve_extractor.export_fbx"
    bl_label = "导出面片 FBX（给 UE）"
    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={"HIDDEN"})

    def execute(self, context):
        result = _LAST.get("result")
        if not result or not result.curves:
            self.report({"ERROR"}, "请先提取")
            return {"CANCELLED"}
        core.export_card_fbx(result, self.filepath, scale=context.scene.curve_extractor.scale)
        self.report({"INFO"}, "已导出 FBX")
        return {"FINISHED"}


class CURVEEXT_OT_export_svg(bpy.types.Operator, ExportHelper):
    bl_idname = "curve_extractor.export_svg"
    bl_label = "导出 SVG"
    filename_ext = ".svg"
    filter_glob: StringProperty(default="*.svg", options={"HIDDEN"})

    def execute(self, context):
        result = _LAST.get("result")
        if not result:
            self.report({"ERROR"}, "请先提取")
            return {"CANCELLED"}
        core.export_svg(result, self.filepath)
        return {"FINISHED"}


class CURVEEXT_OT_export_dxf(bpy.types.Operator, ExportHelper):
    bl_idname = "curve_extractor.export_dxf"
    bl_label = "导出 DXF"
    filename_ext = ".dxf"
    filter_glob: StringProperty(default="*.dxf", options={"HIDDEN"})

    def execute(self, context):
        result = _LAST.get("result")
        if not result:
            self.report({"ERROR"}, "请先提取")
            return {"CANCELLED"}
        core.export_dxf(result, self.filepath)
        return {"FINISHED"}


class CURVEEXT_OT_export_obj(bpy.types.Operator, ExportHelper):
    bl_idname = "curve_extractor.export_obj"
    bl_label = "导出面片 OBJ"
    filename_ext = ".obj"
    filter_glob: StringProperty(default="*.obj", options={"HIDDEN"})

    def execute(self, context):
        result = _LAST.get("result")
        if not result:
            self.report({"ERROR"}, "请先提取")
            return {"CANCELLED"}
        core.export_obj_cards(result, self.filepath, scale=context.scene.curve_extractor.scale)
        return {"FINISHED"}


class CURVEEXT_OT_export_obj_lines(bpy.types.Operator, ExportHelper):
    bl_idname = "curve_extractor.export_obj_lines"
    bl_label = "导出线条 OBJ"
    filename_ext = ".obj"
    filter_glob: StringProperty(default="*.obj", options={"HIDDEN"})

    def execute(self, context):
        result = _LAST.get("result")
        if not result:
            self.report({"ERROR"}, "请先提取")
            return {"CANCELLED"}
        core.export_obj_lines(result, self.filepath)
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
    bg_enabled: BoolProperty(name="自动去背景", default=True)
    bg_tol: FloatProperty(name="背景容差", default=60.0, min=5.0, max=180.0)
    auto_invert: BoolProperty(name="浅色背景自动反色", default=True)
    fine_mode: BoolProperty(name="精细模式（光效）", default=False,
                            description="与网页「精细模式」同一套：精细度75 / 着生80")
    side_path: StringProperty(name="侧面图", default="", subtype="FILE_PATH")
    top_path: StringProperty(name="顶面图", default="", subtype="FILE_PATH")
    trust_top: FloatProperty(name="信顶面", default=0.0, min=0.0, max=100.0,
                             description="0=侧视准，100=俯视准。与网页滑条相同")
    tri_rectify: BoolProperty(name="提取前校正标准三视图", default=True)
    pick_x: FloatProperty(name="补笔 X（像素）", default=0.0)
    pick_y: FloatProperty(name="补笔 Y（像素，从上往下）", default=0.0)


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
        box = layout.box()
        box.label(text="三视图（与网页相同）")
        box.prop(props, "side_path")
        box.prop(props, "top_path")
        box.prop(props, "trust_top")
        box.prop(props, "tri_rectify")
        box.operator("curve_extractor.extract_tri", icon="OUTLINER_OB_CAMERA")
        layout.separator()
        layout.label(text="点选补一笔")
        layout.prop(props, "pick_x")
        layout.prop(props, "pick_y")
        layout.operator("curve_extractor.pick_stroke", icon="EYEDROPPER")
        layout.separator()
        layout.operator("curve_extractor.import_json", icon="IMPORT")
        layout.operator("curve_extractor.export_json", icon="EXPORT")
        layout.operator("curve_extractor.export_fbx", icon="EXPORT")
        layout.operator("curve_extractor.export_obj", icon="EXPORT")
        layout.operator("curve_extractor.export_obj_lines", icon="EXPORT")
        layout.operator("curve_extractor.export_svg", icon="EXPORT")
        layout.operator("curve_extractor.export_dxf", icon="EXPORT")
        layout.separator()
        layout.label(text="提取（与网页同一套参数）")
        layout.prop(props, "fine_mode")
        layout.prop(props, "bg_enabled")
        layout.prop(props, "bg_tol")
        layout.prop(props, "auto_invert")
        layout.prop(props, "bright_thresh")
        layout.prop(props, "hue_min")
        layout.prop(props, "hue_max")
        layout.prop(props, "sat_min")
        layout.prop(props, "branch_detail")
        layout.prop(props, "branch_attach")
        layout.prop(props, "growth_axis")
        layout.prop(props, "min_length")
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
    CURVEEXT_OT_extract_tri,
    CURVEEXT_OT_pick_stroke,
    CURVEEXT_OT_import_json,
    CURVEEXT_OT_export_json,
    CURVEEXT_OT_export_fbx,
    CURVEEXT_OT_export_obj,
    CURVEEXT_OT_export_obj_lines,
    CURVEEXT_OT_export_svg,
    CURVEEXT_OT_export_dxf,
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
