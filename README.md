# Curve Extractor — 金色光带曲线提取工具

从发光流线图像中**准确识别曲线布局**，生成**数学上平滑的矢量曲线**（SVG/JSON），用于 3D 面片枝条生长动画。

## 核心方法

```
原图 → HSV金色掩码 → 形态学固化(填补空洞+合并丝缕) → 骨架化 → 修剪毛刺
     → 多源BFS最短路径(从底部根区域) → 端点角度聚类(5组) → B样条平滑
     → 导出 SVG / JSON
```

### 为什么不用直接追踪？
光带内部有丝缕纹理和空洞，骨架化后中心区域形成复杂网状结构，像素级追踪会在交点处迷路。BFS 最短路径 + 角度聚类能稳定区分 5 根主枝条。

## 工作区结构

```
curve-extractor/
├── input/
│   └── original.png          # 原始参考图
├── src/
│   ├── preprocess.py         # 图像预处理：掩码、固化、骨架化、修剪
│   ├── trace_angle.py        # 多源BFS + 角度聚类（稳定版核心）
│   └── smooth.py             # B样条平滑拟合
├── scripts/
│   └── extract_v07.py        # v0.7 主入口（推荐使用）
├── output/
│   └── v0.7/                 # 产物：SVG / JSON / 预览图
├── .gitignore
└── README.md
```

## 版本历史

| 版本 | 方法 | 曲线数 | 问题 |
|------|------|--------|------|
| v0.1 | 简单骨架追踪 | 39条碎曲线 | 丝缕纹理导致大量分支 |
| v0.2 | +形态学固化 | 16条 | 中心交点处截断 |
| v0.3 | +交点穿越 | 8条 | 中心网状结构迷路 |
| v0.4 | +目标点引导 | 8条 | 交点数耗尽 |
| v0.5 | BFS最短路径 | 4条 | 去重太激进 |
| v0.6 | 宽松去重 | 3条 | 根区域过大 |
| **v0.7** | **BFS + 角度聚类** | **5根主枝条** | **稳定版 ✓** |

## 环境依赖

```bash
pip install numpy scipy scikit-image pillow matplotlib
```

## 使用方法

```bash
# 运行稳定版（v0.7）
python scripts/extract_v07.py

# 输出在 output/v0.7/
#   curves_5branches.svg   — 5根曲线的矢量SVG
#   curves_5branches.json  — 曲线点坐标数据（可导入Blender/C4D）
#   preview.png            — 预览对比图
```

## JSON 数据格式

```json
{
  "version": "v0.7",
  "curve_count": 5,
  "curves": [
    {
      "key": "right_lower",
      "name": "右下卷曲枝",
      "point_count": 800,
      "total_length_px": 1234.56,
      "endpoint_xy": [x, y],
      "points": [[x1, y1], [x2, y2], ...]
    }
  ]
}
```

## 5根主枝条

1. **左上大枝** — 向左上方舒展的长光带
2. **左下卷曲枝** — 向左下方回旋卷曲的枝条
3. **中间主干** — 中心汇聚向上的主根
4. **右上大枝** — 向右上方舒展的长光带
5. **右下卷曲枝** — 向右下方回旋卷曲的枝条

## 3D 使用示例（Blender Python）

```python
import json, bpy

data = json.load(open("output/v0.7/curves_5branches.json"))
for curve in data["curves"]:
    pts = [(p[0] * 0.01, p[1] * 0.01, 0) for p in curve["points"]]
    # 创建曲线对象并设置点...
    print(f"{curve['name']}: {curve['point_count']} points")
```

## Git 版本管理

```bash
git tag               # 查看所有版本标签
git log --oneline     # 查看提交历史
git checkout <tag>    # 回滚到指定版本
```
