# Curve Extractor — Houdini operators (internal)

from __future__ import annotations

import os
import time

import numpy as np

from . import core


def _ask_file(title, pattern, multiple=False):
    import hou

    path = hou.ui.selectFile(
        title=title,
        file_type=hou.fileType.Any,
        pattern=pattern,
        multiple_select=multiple,
    )
    if not path:
        return None
    return hou.expandString(path)


def _yup_points(entry, scale):
    pts = []
    for x, y, z in entry.points3d:
        ux, uy, uz = core.html_world_to_yup(float(x), float(y), float(z))
        pts.append((ux * scale, uy * scale, uz * scale))
    return pts


def _clear_geo(obj):
    for child in list(obj.children()):
        child.destroy()


def _create_geo(name):
    import hou

    parent = hou.node("/obj")
    obj = parent.createNode("geo", name)
    _clear_geo(obj)
    return obj


def _fill_geometry(geo, result, scale, make_cards):
    import hou

    if geo.findPrimAttrib("name") is None:
        geo.addAttrib(hou.attribType.Prim, "name", "")
    if geo.findPrimAttrib("ce_level") is None:
        geo.addAttrib(hou.attribType.Prim, "ce_level", 1)

    for i, entry in enumerate(result.curves):
        pts = _yup_points(entry, scale)
        if len(pts) < 2:
            continue
        poly = geo.createPolygon()
        poly.setIsClosed(False)
        created = []
        for p in pts:
            pt = geo.createPoint()
            pt.setPosition(hou.Vector3(p))
            created.append(pt)
            poly.addVertex(pt)
        poly.setAttribValue("name", entry.name)
        poly.setAttribValue("ce_level", int(entry.level))

        if make_cards:
            card = result.card
            sheets = core.build_card_sheets(entry.points3d, card, scale=scale)
            for verts, faces, uvs in sheets:
                bverts = []
                for vx, vy, vz in verts:
                    ux, uy, uz = core.html_world_to_yup(vx / scale, vy / scale, vz / scale)
                    bverts.append((ux * scale, uy * scale, uz * scale))
                houdini_pts = []
                for p in bverts:
                    pt = geo.createPoint()
                    pt.setPosition(hou.Vector3(p))
                    houdini_pts.append(pt)
                uv_attr = geo.findVertexAttrib("uv")
                if uv_attr is None:
                    geo.addAttrib(hou.attribType.Vertex, "uv", hou.Vector3(0, 0, 0))
                for a, b, d, c in faces:
                    prim = geo.createPolygon()
                    prim.setIsClosed(True)
                    for vi in (a, b, d, c):
                        prim.addVertex(houdini_pts[vi])
                    for vi, vtx in zip((a, b, d, c), prim.vertices()):
                        vtx.setAttribValue("uv", hou.Vector3(uvs[vi][0], uvs[vi][1], 0))


def _params_from_dialog():
    import hou

    buttons = ("提取", "取消")
    # Defaults match web v1.4.25
    result = hou.ui.readMultiInput(
        "Curve Extractor 参数",
        (
            "亮度阈值 0.15-1",
            "枝条精细度 0-100",
            "分叉着生 0-100",
            "走势轴向 0-100（左横向/右竖向）",
            "像素缩放",
            "面片数量 1-4",
            "面片半宽(像素)",
        ),
        initial_contents=("0.70", "40", "70", "50", "0.01", "2", "24"),
        buttons=buttons,
        default_choice=0,
        close_choice=1,
    )
    if result[0] != 0:
        return None
    vals = result[1]
    params = core.ExtractParams(
        bright_thresh=float(vals[0]),
        branch_detail=float(vals[1]),
        branch_attach=float(vals[2]),
        growth_axis=float(vals[3]),
    )
    card = core.CardParams(count=int(float(vals[5])), width=float(vals[6]))
    scale = float(vals[4])
    return params, card, scale


def extract_from_image_dialog():
    import hou

    path = _ask_file("选择光效或线稿图（仅本地，勿外传）", "*.png *.jpg *.jpeg *.tif *.tiff *.exr *.bmp")
    if not path or not os.path.isfile(path):
        return
    parsed = _params_from_dialog()
    if parsed is None:
        return
    params, card, scale = parsed
    hou.setStatusMessage("Curve Extractor 提取中…")
    t0 = time.time()
    try:
        try:
            result = core.extract_from_path(path, params, card)
        except Exception:
            rgb = _load_via_cops(path)
            result = core.extract_from_rgb(rgb, params, card)
    except Exception as e:
        hou.ui.displayMessage("提取失败：%s" % e, severity=hou.severityType.Error)
        return
    if not result.curves:
        hou.ui.displayMessage("没有提出曲线。可提高枝条精细度或降低亮度阈值。")
        return
    name = "ce_" + os.path.splitext(os.path.basename(path))[0]
    obj = _create_geo(name)
    _inject_geometry(obj, result, scale, True)
    ms = int((time.time() - t0) * 1000)
    hou.setStatusMessage(
        "提取完成：%d 根 · %s · %dms" % (len(result.curves), "线稿" if result.line_drawing else "光效", ms)
    )
    hou.ui.displayMessage(
        "已生成 /obj/%s\n%d 条曲线（内部工具，结果勿上传公网）" % (obj.name(), len(result.curves))
    )


def _inject_geometry(obj, result, scale, make_cards):
    sop = obj.node("extract") or obj.createNode("python", "extract")
    sop.parm("python").set(_geometry_as_python(result, scale, make_cards))
    out = obj.node("OUT") or obj.createNode("null", "OUT")
    out.setInput(0, sop)
    out.setDisplayFlag(True)
    out.setRenderFlag(True)
    obj.layoutChildren()


def _geometry_as_python(result, scale, make_cards):
    payload = result.to_json_dict()
    import json

    blob = json.dumps(payload, ensure_ascii=False)
    return """
import json
import numpy as np
from curve_extractor import core
import hou

data = json.loads(%r)
result = core.result_from_json(data)
geo = hou.pwd().geometry()
geo.clear()
from curve_extractor.houdini_ops import _fill_geometry
_fill_geometry(geo, result, %s, %s)
""" % (blob, scale, make_cards)


def _load_via_cops(path):
    import hou

    img = hou.node("/img")
    if img is None:
        raise RuntimeError("No /img context")
    net = img.createNode("img", "ce_tmp_load")
    try:
        file_cop = net.createNode("file")
        if file_cop.parm("filename1"):
            file_cop.parm("filename1").set(path)
        elif file_cop.parm("filename"):
            file_cop.parm("filename").set(path)
        file_cop.cook(force=True)
        w, h = file_cop.xRes(), file_cop.yRes()
        pix = file_cop.allPixels("C")
        arr = np.asarray(pix, dtype=np.float32).reshape(h, w, 3)
        arr = arr[::-1]
        return (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    finally:
        try:
            net.destroy()
        except Exception:
            pass


def import_json_dialog():
    import hou

    path = _ask_file("导入 Curve Extractor JSON", "*.json")
    if not path or not os.path.isfile(path):
        return
    scale_s = hou.ui.readInput("像素缩放", buttons=("确定", "取消"), initial_contents="0.01")
    if scale_s[0] != 0:
        return
    scale = float(scale_s[1])
    result = core.load_json_file(path)
    if not result.curves:
        hou.ui.displayMessage("JSON 里没有曲线", severity=hou.severityType.Error)
        return
    obj = _create_geo("ce_json")
    _inject_geometry(obj, result, scale, True)
    hou.ui.displayMessage("导入 %d 条曲线到 /obj/%s" % (len(result.curves), obj.name()))


def export_selected_json():
    import hou

    sel = hou.selectedNodes()
    geos = []
    for n in sel:
        if n.type().category().name() == "Object" and n.displayNode():
            geos.append(n.displayNode().geometry())
        elif n.type().category().name() == "Sop":
            geos.append(n.geometry())
    if not geos:
        hou.ui.displayMessage("请先选中带曲线的 OBJ 或 SOP")
        return
    path = hou.ui.selectFile(title="导出 JSON", pattern="*.json", chooser_mode=hou.fileChooserMode.Write)
    if not path:
        return
    path = hou.expandString(path)
    if not path.lower().endswith(".json"):
        path += ".json"
    scale = 0.01
    result = core.ExtractResult()
    idx = 0
    for geo in geos:
        for prim in geo.prims():
            if prim.numVertices() < 2:
                continue
            pts = []
            for v in prim.vertices():
                p = v.point().position()
                # inverse yup: x=x, y=-y, z=z  then /scale
                pts.append([p[0] / scale, -p[1] / scale, p[2] / scale])
            idx += 1
            result.curves.append(
                core.ExtractedCurve(
                    key="curve_%02d" % idx,
                    name="Curve %02d" % idx,
                    points_yx=np.asarray(pts, dtype=np.float64)[:, :2],
                    points3d=np.asarray(pts, dtype=np.float64),
                    level=1,
                    color_rgb=(255, 215, 0),
                )
            )
    if not result.curves:
        hou.ui.displayMessage("没有可导出的折线")
        return
    core.save_json_file(result, path)
    hou.ui.displayMessage("已导出 %d 条到\n%s" % (len(result.curves), path))
