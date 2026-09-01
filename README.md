# Curve Extractor — 金色光带曲线提取工具

网页端工具：从发光枝条/光效图中自动识别曲线走向，生成平滑矢量曲线，并在曲线上生成十字交叉面片（Plane），导出 FBX/OBJ 导入 UE 做枝条生长动画。

## 快速开始

直接用浏览器打开 `app.html` 即可，无需安装任何依赖。

线上地址：https://yuculikedogandfish-droid.github.io/curve-extractor/app.html

## 功能

- **单图识别**：上传一张正面图，自动提取曲线
- **三视图识别**：上传正面/侧面/顶面；正交对照；「信顶面」滑条在侧视准 / 俯视准之间折中
- **线稿**：按走向惯性穿过交叉口；可在「曲线」页点选补一笔
- **交互式曲线编辑**：拖拽拐点
- **3D 面片预览**：1/2/3/4 片，UV 正确
- **导出**：FBX / OBJ / JSON / SVG / DXF

## 使用流程

1. 选择单图或三视图模式，上传图片
2. 点"提取曲线"，查看各阶段预览（掩码→骨架→曲线→3D）
3. 调整左侧参数（亮度阈值、形态学、面片宽度等）优化效果
4. 在曲线编辑器里手动微调走向
5. 导出 FBX，导入 UE

## 技术栈

- 纯前端单文件（`app.html`），HTML + CSS + JS，无外部依赖
- 3D 预览用 Canvas 2D 自绘投影（不用 Three.js）
- 图像处理：HSV 掩码、形态学、Zhang-Suen 骨架化、BFS、B 样条
- 部署：GitHub Pages，push 到 master 自动部署

## 项目结构

```
curve-extractor/
├── app.html              # 主文件（唯一需要编辑的）
├── HANDOFF.md            # 交接文档（详细模块说明，给 Cursor 用）
├── index.html            # Pages 入口
├── input/                # 测试素材
│   ├── run_tri.py        # 自动化测试脚本
│   ├── tri/              # 两组三视图素材
│   └── tri_labeled/      # 处理后的测试素材（processed_nolabel/ 推荐用）
└── archive/              # 旧版本归档（不要动）
```

## 开发与上线

- 日常改代码推 **`dev`**；**`master`** 才是 GitHub Pages 线上。
- 详细模块说明：[HANDOFF.md](./HANDOFF.md)
- **版本、问题、回滚**：[VERSIONS.md](./VERSIONS.md)

```bash
# 本地：直接打开 app.html
git checkout dest
git add app.html
git commit -m "v1.4.xx: 为什么改"
git push origin dest

# 上线（确认后再做）
git checkout master && git merge dest && git push origin master
```

## 当前版本

**v1.4.19** — 线稿三视图：走向过交叉口、侧视连续取 Z、墨水包围盒对齐、「信顶面」滑条在侧视/俯视之间折中。

回滚：`git checkout v1.4.18 -- app.html`（tag 一览见 VERSIONS.md）。
