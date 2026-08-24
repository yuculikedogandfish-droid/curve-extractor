# UE Python 导入脚本 — 由 Curve Extractor 生成
# 在 UE 编辑器中运行：窗口 -> 开发者工具 -> Python 脚本，或用 py 命令执行
import json
import unreal

# 读取 Spline 数据
with open(r"output/v1.0/original_ue_spline.json", "r", encoding="utf-8") as f:
    data = json.load(f)

world = unreal.EditorLevelLibrary.get_editor_world()

# 创建 Actor
actor_class = unreal.EditorLevelLibrary.spawn_actor_from_class(
    unreal.StaticMeshActor, unreal.Vector(0, 0, 0)
)
actor.set_actor_label("CurveExtractor_original")

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
    print(f"  Created spline: {curve_data['name']} ({curve_data['point_count']} points)")

print(f"\nImport complete: {data['curve_count']} curves imported to {actor_name}")
