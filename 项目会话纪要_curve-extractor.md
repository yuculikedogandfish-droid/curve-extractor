# 金色光带曲线提取工具 — 项目会话纪要

> **项目名称**：curve-extractor  
> **创建日期**：2026-08-20  
> **当前版本**：v0.8（稳定版）  
> **文档用途**：递交给项目 Agent，用于后续开发衔接

---

## 一、项目概述

从金色发光流线图像中**准确识别曲线布局**，生成**数学上极光滑的矢量曲线**（SVG/JSON），用于 3D 面片（Plane）枝条生长动画。

### 原始参考图
- 尺寸：1672 × 941 像素
- 内容：黑色背景上的 5 根金色发光丝缕状光带，从底部中心向五个方向发散

### 5 根主枝条定义
| 编号 | key | 名称 | 端点方向 | 说明 |
|------|-----|------|---------|------|
| 1 | `left_upper` | 左上大枝 | -149° | 向左上方舒展的长光带 |
| 2 | `left_lower` | 左下卷曲枝 | -172° | 向左下方回旋卷曲的枝条 |
| 3 | `center_top` | 中间主干 | -89° | 中心汇聚向上的主根 |
| 4 | `right_upper` | 右上大枝 | -57° | 向右上方舒展的长光带 |
| 5 | `right_lower` | 右下卷曲枝 | -1° | 向右下方回旋卷曲的枝条 |

---

## 二、技术管线总览

```
原图 (PNG)
  │
  ├─ 1. HSV 金色掩码提取
  │     └─ 色相 0.05~0.17 + 饱和度≥0.25 + 亮度≥0.25，亮度≥0.70 兜底
  │
  ├─ 2. 形态学固化 (solidify)
  │     ├─ 去小连通块 (min_size=800)
  │     ├─ 大核闭运算 (disk=10) — 填补内部空洞
  │     ├─ 膨胀 (disk=3) — 合并邻近丝缕
  │     └─ 再次去小连通块
  │
  ├─ 3. 骨架化 (skeletonize)
  │     └─ 实心光带 → 单像素宽中心线
  │
  ├─ 4. 修剪短毛刺 (prune)
  │     └─ 迭代去除长度<25px 的端部分支
  │
  ├─ 5. 多源 BFS 最短路径
  │     ├─ 根区域：底部 28% (y≥72%) 所有骨架像素
  │     ├─ 多源 BFS 计算每个骨架像素到根的距离场
  │     └─ 每个端点沿距离递减方向走到根 → 最短路径
  │
  ├─ 6. 端点角度聚类
  │     ├─ 以汇聚中心 (x=50%, y=65%) 为原点计算端点角度
  │     ├─ 5 个角度区间对应 5 根主枝条
  │     └─ 每组取最长路径
  │
  ├─ 7. RDP 路径简化 (v0.8 新增)
  │     └─ epsilon=8px，去掉所有局部锯齿点，只保留宏观拐点 (10~15 个/根)
  │
  └─ 8. B 样条插值
        └─ 三次 B 样条 (k=3, smooth=0) 精确通过拐点 → 800 个 C2 连续光滑点
              │
              ▼
         产物：SVG / JSON / HTML 交互页 / 对比图
```

---

## 三、版本迭代历史

| 版本 | 核心方法 | 曲线数 | 主要问题 | 状态 |
|------|---------|--------|---------|------|
| v0.1 | 简单骨架追踪 + 直接B样条 | 39条碎曲线 | 光带丝缕纹理导致大量分支 | 已废弃 |
| v0.2 | +形态学固化 (close=10, dilate=3) | 16条 | 中心交点处截断 | 已废弃 |
| v0.3 | +交点穿越追踪 (方向连续性) | 8条 | 中心网状结构迷路 | 已废弃 |
| v0.4 | +目标点引导 (底部中心) | 8条 | 交点数耗尽 (max=8) | 已废弃 |
| v0.5 | 多源BFS最短路径 | 4条 | 去重太激进 (threshold=0.45) | 已废弃 |
| v0.6 | 宽松去重 + 扩大根区域 | 3条 | 根区域过大，路径重叠 | 已废弃 |
| v0.7 | BFS + 端点角度聚类 | 5根 ✓ | 曲线仍有局部锯齿 | 保留对比 |
| **v0.8** | **BFS + 角度聚类 + RDP简化 + B样条插值** | **5根 ✓** | **极光滑宏观走向** | **当前稳定版** |

### 关键突破点
1. **v0.2 形态学固化**：解决了光带内部丝缕纹理导致骨架碎片化的问题
2. **v0.5 多源BFS**：解决了像素级追踪在中心网状结构迷路的问题
3. **v0.7 角度聚类**：解决了5根枝条在中心共享路径导致去重合并的问题
4. **v0.8 RDP简化**：解决了BFS路径沿骨架像素走产生局部锯齿的问题

---

## 四、v0.8 最终方案详解

### 4.1 RDP (Ramer-Douglas-Peucker) 路径简化

**算法原理**：
1. 连接路径起点和终点形成线段
2. 找到路径上距离该线段最远的点
3. 若最远距离 > epsilon（阈值），保留该点，递归处理左右两段
4. 若最远距离 ≤ epsilon，丢弃中间所有点，只保留首尾

**参数**：`epsilon = 8.0`（像素）

**效果**：每根枝条从几百个像素点简化为 10~15 个宏观拐点，完全去除局部锯齿。

### 4.2 B 样条插值

**参数**：
- 阶数 `k = 3`（三次 B 样条，C2 连续）
- 平滑因子 `s = 0.0`（精确通过所有 RDP 拐点）
- 输出采样数 `num_samples = 800`

**效果**：在 10~15 个拐点之间生成 800 个光滑点，曲线在拐点处 C2 连续（曲率连续），无任何折角。

### 4.3 5 根枝条的拐点统计

| 枝条 | 原始BFS点数 | RDP拐点 | 光滑输出 | 总弧长(px) |
|------|------------|---------|---------|------------|
| 右下卷曲枝 | 667 | 10 | 800 | — |
| 右上大枝 | 699 | 15 | 800 | — |
| 中间主干 | 476 | 11 | 800 | — |
| 左上大枝 | 650 | 13 | 800 | — |
| 左下卷曲枝 | 793 | 13 | 800 | — |

---

## 五、产物清单

### 5.1 本地工作区 (`H:\tool\curve-extractor\`)

```
curve-extractor/
├── index.html                          # GitHub Pages 入口（交互查看器）
├── README.md                           # 项目说明文档
├── .gitignore
├── .github/workflows/pages.yml         # GitHub Actions 部署工作流
├── input/
│   └── original.png                    # 原始参考图 (1672×941)
├── src/
│   ├── preprocess.py                   # 预处理：掩码、固化、骨架化、修剪
│   ├── trace_angle.py                  # 多源BFS + 端点角度聚类
│   └── smooth.py                       # RDP简化 + B样条插值 + 传统平滑
├── scripts/
│   ├── extract_v07.py                  # v0.7 入口（直接B样条，保留对比）
│   └── extract_v08.py                  # v0.8 入口（当前稳定版）
└── output/
    ├── v0.7/
    │   ├── curves_5branches.svg
    │   ├── curves_5branches.json
    │   ├── index.html
    │   └── preview.png
    └── v0.8/
        ├── curves_5branches.svg        # 矢量曲线（5根不同颜色）
        ├── curves_5branches.json       # 曲线点坐标数据（含RDP拐点）
        └── comparison_v07_vs_v08.png   # v0.7 vs v0.8 平滑度对比图
```

### 5.2 JSON 数据格式

```json
{
  "version": "v0.8",
  "curve_count": 5,
  "curves": [
    {
      "key": "right_lower",
      "name": "右下卷曲枝",
      "point_count": 800,
      "total_length_px": 1234.56,
      "raw_length": 667,
      "rdp_control_points": 10,
      "control_points": [[x, y], ...],
      "endpoint_xy": [x, y],
      "angle_deg": -1.3,
      "points": [[x1, y1], [x2, y2], ...]
    }
  ]
}
```

- `points`：800 个光滑曲线点，格式 `[x, y]`（图像坐标系，原点左上角）
- `control_points`：RDP 简化后的宏观拐点
- `total_length_px`：曲线总弧长（像素）

### 5.3 SVG 格式
- 5 根曲线分别为不同颜色（红/青/蓝/橙/浅绿）
- 黑色背景，stroke-width=3，圆角线帽
- 每根曲线有 `id` 和 `name` 属性

---

## 六、工作区与版本管理

### 6.1 本地 Git
- 仓库路径：`H:\tool\curve-extractor\.git`
- 分支：`master`
- 标签：`v0.7`、`v0.8`

```bash
cd H:\tool\curve-extractor
git log --oneline          # 查看提交历史
git tag                    # 查看版本标签
git checkout v0.7          # 回滚到 v0.7
git checkout v0.8          # 切换到当前稳定版
```

### 6.2 GitHub 远程仓库
- **仓库地址**：https://github.com/yuculikedogandfish-droid/curve-extractor
- 可见性：公开 (Public)
- 远程别名：`origin`
- 已推送：master 分支 + v0.7/v0.8 标签

### 6.3 GitHub Pages 线上交互页
- **访问地址**：https://yuculikedogandfish-droid.github.io/curve-extractor/
- 部署方式：GitHub Actions (`.github/workflows/pages.yml`)
- 触发条件：push 到 master 分支自动部署
- 功能：
  - 5 根曲线不同颜色展示
  - 悬停曲线显示名称、点数等详情
  - 滚轮缩放、拖拽平移
  - 侧栏开关单根曲线显示/隐藏
  - Reset View / Show All / Hide All 控制按钮

---

## 七、关键参数调优指南

### 7.1 运行命令
```bash
cd H:\tool\curve-extractor
python scripts/extract_v08.py
```

### 7.2 可调参数（位于 `scripts/extract_v08.py`）

| 参数 | 默认值 | 位置 | 说明 |
|------|--------|------|------|
| `close_radius` | 10 | solidify_mask() | 形态学闭运算核半径，越大填补空洞越强 |
| `dilate_radius` | 3 | solidify_mask() | 膨胀核半径，越大越容易合并邻近丝缕 |
| `min_branch_length` | 25 | prune_skeleton() | 短毛刺修剪阈值，越大修剪越激进 |
| `root_y_ratio` | 0.72 | extract_5_main_curves() | 根区域起始位置（图像高度比例），越小根区域越大 |
| `rdp_epsilon` | 8.0 | smooth_trend_curve() | **RDP简化阈值，越大拐点越少曲线越光滑（可能偏离原图）** |
| `b_spline_smooth` | 0.0 | smooth_trend_curve() | B样条平滑因子，0=精确通过拐点，>0=进一步平滑 |
| `num_samples` | 800 | smooth_trend_curve() | 输出曲线采样点数 |

### 7.3 调优建议
- **曲线不够光滑**：增大 `rdp_epsilon`（如 10→15），或增大 `b_spline_smooth`（如 0→50）
- **曲线偏离原图**：减小 `rdp_epsilon`（如 8→5），保留更多拐点
- **某根枝条未识别**：检查角度区间 `ANGLE_GROUPS`（位于 `src/trace_angle.py`），调整 min/max
- **中心区域曲线异常**：调整 `root_y_ratio`（如 0.72→0.65），扩大根区域

---

## 八、环境依赖

### Python 包
```
numpy >= 2.0
scipy >= 1.18
scikit-image >= 0.26
pillow >= 12.0
matplotlib >= 3.11
```

### 运行环境
- Python 3.13（已验证）
- Windows / macOS / Linux 均可
- 无需 GPU，纯 CPU 运算，单次运行约 10-30 秒

---

## 九、后续可扩展方向

### 9.1 3D 面片生长（核心目标）
- 沿曲线法线方向扩展宽度，生成带状面片几何
- 为每根曲线生成沿路径的渐变透明度贴图（生长遮罩）
- Blender Python 脚本：直接导入 JSON 生成 BezierCurve + 生长动画
- 面片 UV 映射：曲线方向为 U，宽度方向为 V

### 9.2 曲线质量提升
- 自适应 RDP epsilon：根据曲线局部曲率动态调整阈值
- 多尺度平滑：保留大趋势的同时保留中等尺度的弯曲
- 光带宽度提取：结合距离变换，提取每根光带的宽度变化，用于面片宽度

### 9.3 交互工具
- 在线编辑器：网页端拖拽调整 RDP 拐点，实时预览曲线
- 曲线微调：手动修正某根曲线的走向
- 批量处理：支持多张图片批量提取曲线

### 9.4 工程化
- 打包为 Python 包（pip install curve-extractor）
- CLI 工具：`curve-extract input.png --output out/ --epsilon 8`
- 单元测试 + CI/CD
- API 服务：FastAPI 封装，支持上传图片返回曲线数据

---

## 十、核心源码文件说明

### `src/preprocess.py`
- `load_image()`：加载图片为 RGB numpy 数组
- `extract_golden_mask()`：HSV 空间提取金色光带二值掩码
- `solidify_mask()`：形态学固化（去噪→闭运算→膨胀→去噪）
- `skeletonize()`：骨架化（实心带→单像素中心线）
- `prune_skeleton()`：迭代修剪短毛刺分支

### `src/trace_angle.py`
- `find_endpoints()`：找到骨架所有端点（degree=1）
- `define_root_region()`：定义底部中心根区域
- `multi_source_bfs()`：多源 BFS 计算距离场
- `trace_path_to_root()`：从端点沿距离递减走到根
- `extract_5_main_curves()`：角度聚类提取5根主枝条
- `ANGLE_GROUPS`：5个角度区间定义（可调）

### `src/smooth.py`
- `rdp_simplify()`：RDP 路径简化算法
- `smooth_trend_curve()`：**v0.8 核心** — RDP简化 + B样条插值
- `smooth_curve()`：传统直接B样条平滑（v0.7用，保留对比）
- `moving_average_curve()`：移动平均平滑（兜底）

### `scripts/extract_v08.py`
- 主入口，串联完整管线
- 生成 SVG / JSON / 对比图
- 包含 v0.7 vs v0.8 对比图生成逻辑

---

## 附录：会话关键决策记录

1. **为什么不用 AI 直接出图？** — AI 重绘无法保证曲线走向与原图一致，且产生的是位图不是矢量曲线
2. **为什么不用 OpenCV？** — 运行环境 pip 源不可用，scikit-image 已预装且功能足够
3. **为什么用 BFS 而不是 DFS 追踪？** — 骨架中心区域是复杂网状结构，DFS 会在交点迷路，BFS 最短路径保证沿骨架走且全局最优
4. **为什么用角度聚类而不是按长度去重？** — 5根枝条在中心共享路径，按重叠度去重会合并掉不同枝条；按端点方向聚类能精确区分
5. **为什么 v0.8 加 RDP？** — BFS 路径沿骨架像素走，骨架本身有锯齿，直接B样条平滑后仍有局部波动；RDP 先去掉所有锯齿点只留宏观拐点，再插值得到极光滑曲线

---

*文档生成时间：2026-08-21*  
*对应代码版本：v0.8 (commit 58d67f5)*  
*GitHub: https://github.com/yuculikedogandfish-droid/curve-extractor*
