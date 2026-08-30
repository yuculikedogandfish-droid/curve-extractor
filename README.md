# Curve Extractor — 金色光带曲线提取工具

网页端工具：从发光枝条/光效图中自动识别曲线走向，生成平滑矢量曲线，并在曲线上生成十字交叉面片（Plane），导出 FBX/OBJ 导入 UE 做枝条生长动画。

## 快速开始

直接用浏览器打开 `app.html` 即可，无需安装任何依赖。

线上地址：https://yuculikedogandfish-droid.github.io/curve-extractor/app.html

## 功能

- **单图识别**：上传一张正面图，自动提取曲线
- **三视图识别**：上传正面/侧面/顶面，三角测量还原 3D 曲线（支持拖拽上传）
- **交互式曲线编辑**：拖拽曲线上的控制点调整走向
- **3D 面片预览**：沿曲线中心轴生成面片（1/2/3/4 片可选），UV 正确
- **多格式导出**：FBX / OBJ / JSON / SVG / DXF

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

## 开发

详细的模块说明、函数索引、参数表、版本历史见 **[HANDOFF.md](./HANDOFF.md)**。

```bash
# 本地预览：直接双击 app.html
# 部署：
git add app.html
git commit -m "改动说明"
git push origin master
```

## 当前版本

**v1.4** — 算法回滚到 v1.1（稳定版）+ 三视图拖拽上传。

详见 HANDOFF.md 的版本历史。
