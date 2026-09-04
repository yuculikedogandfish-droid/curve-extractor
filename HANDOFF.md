# Curve Extractor — 交接文档（Agent / 同事接手用）

> **当前版本**：v1.4.22  
> **最后更新**：2026-09-05  
> **开发分支**：`dev`（日常 push）  
> **线上分支**：`master`（GitHub Pages）  
> **线上地址**：https://yuculikedogandfish-droid.github.io/curve-extractor/app.html  
> **仓库**：https://github.com/yuculikedogandfish-droid/curve-extractor  
> **版本台账与回滚**：**[VERSIONS.md](./VERSIONS.md)**（各 tag、已知问题、怎么回滚，先读这个）

---

## 一、项目是什么

给公司特效师用的**网页端曲线提取工具**：上传一张发光枝条/光效图，自动识别曲线走向，生成平滑矢量曲线，并在曲线上生成十字交叉面片（Plane），可导出为 FBX/OBJ/JSON/SVG/DXF，导入 UE（虚幻引擎）做枝条生长动画。

**两种输入模式**：
1. **单图识别**：上传一张正面图，曲线在 2D 平面上，深度由算法估算
2. **三视图识别**：上传正面/侧面/顶面三张图，三角测量还原 3D 曲线（更准确）

**核心交付物**：沿曲线中心轴分布的面片网格（默认十字交叉 2 片，可选 1/2/3/4 片），UV 正确，暂不做贴图（由特效师后续处理）。

---

## 二、技术栈

- **纯前端单文件**：`app.html`（HTML + CSS + JS 全在一个文件里，约 1.5MB，含内嵌 demo 图 base64）
- **无外部依赖**：不用 Three.js，3D 预览用 Canvas 2D 自绘投影（`projectWorld` 函数做透视投影）
- **图像处理**：纯 JS 实现，HSV 颜色空间、形态学（膨胀/腐蚀/闭运算）、Zhang-Suen 骨架化、BFS、B 样条插值
- **部署**：GitHub Pages，push 到 master 自动部署（`.github/workflows/pages.yml`）
- **本地预览**：直接双击 `app.html` 用浏览器打开即可，无需服务器

---

## 三、文件结构

```
curve-extractor/
├── app.html                  # 网页主文件
├── blender_addon/            # Blender 插件（导入 JSON）
├── index.html                # GitHub Pages 入口（重定向到 app.html）
├── README.md                 # 项目说明（需更新，当前是旧Python版）
├── .gitignore
├── .github/workflows/pages.yml  # GitHub Actions 部署
├── input/                    # 测试素材
│   ├── run_tri.py            # 三视图自动化测试脚本（Python + Playwright）
│   ├── tri/                  # 两组三视图原始素材 + base64（g1/g2_front/side/top.txt）
│   └── tri_labeled/          # 标注/处理后的三视图素材
│       ├── raw/              # 用户原始上传图
│       ├── processed/        # 处理后（纯黑底，带视图标注文字）
│       ├── processed_nolabel/ # 处理后（纯黑底，无标注，推荐测试用）
│       ├── process.py        # 素材预处理脚本（去背景/缩放/标注）
│       └── debug/            # 调试截图（可随时清空）
└── archive/                  # 归档（不要动）
    ├── legacy_python/        # 旧 Python 版本（v0.1-v0.8），已废弃
    └── debug_screenshots/    # 历史调试截图
```

**网页只改 `app.html`。** Blender 插件改 `blender_addon/`。其他是素材和归档。

---

## 四、app.html 核心模块（按行号区域）

> 所有函数都在 `<script>` 标签内，全局变量 `S` 是状态对象。

### 4.1 状态与 UI（约 430-580 行）
- `S`：全局状态对象，存所有中间数据（rgb/mask/skeleton/curves/cardMeshes 等）
- `getParams()`：从 UI 滑条读取参数
- `updateParamLabels()`：同步滑条数值显示
- `setStatus(text)` / `toast(msg,type,dur)` / `setBusy(bool)`：UI 反馈
- `loadImage(file)` / `drawCanvas(id,rgb)` / `drawBinary(id,buf,w,h)`：图像加载与绘制

### 4.2 颜色与掩码（约 590-820 行）
- `rgb2hsv(r,g,b)`：RGB 转 HSV
- `estimateBackgroundColor(rgb)`：估算背景色（用于非纯色背景去除）
- `buildBackgroundMask()` / `computeMaskFromRgb()`：背景去除
- `extractGoldenMask()`：**核心**——从 RGB 提取金色/亮色二值掩码
  - 逻辑：HSV 金色范围（hue 0.05-0.17）+ 亮度兜底（max channel > threshold）
  - 参数：`brightThresh`（亮度阈值，默认 0.45）、`hueMin/hueMax`、`satMin`
- `processTriViews()`：三视图融合（正面为主，侧面/顶面提供深度信息）
- `autoAdaptParams()`：根据掩码连通块特征自动调整形态学参数（v1.1 版本较简单）

### 4.3 形态学（约 900-1100 行）
- `createDisk(r)`：生成圆形结构元素
- `binaryDilate/Erode/Close(buf,w,h,r)`：二值形态学操作
- `removeSmallObjects(buf,w,h,minSize)`：去小连通块
- `solidifyMask()`：**核心**——掩码固化（去小噪点 → 闭运算填洞 → 膨胀合并丝缕 → 再去小噪点）
  - 参数：`closeRadius`（闭运算核，默认 5）、`dilateRadius`（膨胀核，默认 1）、`minObjectSize`（最小对象，默认 800）

### 4.4 骨架化（约 1115-1260 行）
- `zhangSuen(buf,w,h)`：Zhang-Suen 细化算法，实心带 → 单像素中心线
- `pruneSkeleton(skel,w,h,minLen)`：迭代修剪短毛刺分支
  - 参数：`pruneLength`（默认 25）

### 4.5 曲线追踪（约 1270-2900 行，最大的模块）

代码里实现了**多种追踪算法**，通过 `S.traceMode` 切换：

| traceMode | 函数 | 说明 | v1.4 默认 |
|-----------|------|------|-----------|
| `'angle'` | `extract5MainCurves()` | BFS 最短路径 + 端点角度聚类（5 根），最老的方法 | 可选 |
| `'smart'` | `traceAllCurvesSmart()` | 端点+交叉点检测，junction 感知的长曲线追踪 | 可选 |
| `'of'` | `traceOrientationField()` | 方向场追踪，可跨间隙，适合碎裂淡线 | **v1.4 默认** |

**of 模式关键子函数**：
- `computeOrientationField()`：计算骨架方向场
- `traceOrientationField()`：沿方向场追踪曲线
- `connectShortSegments()`：连接短段
- `extractAllEdges()` / `pairEdgesAtJunctions()` / `buildLongCurves()`：边提取与配对

**smart 模式关键子函数**：
- `findEndpointsAndJunctions()`：检测端点和交叉点
- `traceBetweenEndpoints()` / `traceContinuousPath()`：端点间追踪
- `extractAllEdgesV2()` / `pairEdgesGlobal()` / `buildLongCurvesV2()`

**后处理**：
- `deduplicateCurves()`：去重
- `classifyCurves()`：按长度/位置分一级/二级/三级
- `estimateCurveDepths()`：估算深度（单图模式）
- `checkCurveOverlap()`：检测曲线重叠

### 4.6 平滑（约 2930-3100 行）
- `rdpSimplify(points, epsilon)`：RDP 路径简化（去锯齿，保留宏观拐点）
- `bsplineBasis()` / `bsplineInterpolate()`：三次 B 样条插值
- `smoothAllCurves()`：对所有曲线做 RDP + B 样条，输出 800 个光滑点
  - 参数：`smoothEpsilon`（RDP 阈值，默认 8）、`smoothSamples`（输出点数，默认 800）

### 4.7 曲线编辑器（约 3100-3230 行）
- `drawEditor()`：在曲线上绘制可拖拽的控制点
- `editorMouseDown/Move/Up()`：拖拽交互
- `getEditOffset()`：计算编辑偏移
- 用户可手动拖拽曲线上的控制点调整走向

### 4.8 3D 面片生成（约 3240-3560 行）
- `buildCurveWorldPoints()`：2D 曲线点 → 3D 世界坐标（含深度）
- `buildFrames(curve, width)`：沿曲线生成 Frenet 标架（切线/法线/副法线）
- `buildCardMesh(curve, options)`：**核心**——在曲线上生成面片网格
  - 参数：`cardWidth`（面片宽度）、`cardCount`（面片数量，默认 2=十字交叉）、`cardTaper`（末端渐缩）
  - 面片以曲线为中心轴，UV 沿曲线方向分布
- `buildAllCardMeshes()`：为所有曲线生成面片
- `rebuildMeshFor(curveIndex)`：单条曲线重建（编辑后用）

### 4.9 3D 预览（约 3560-3800 行）
- `projectWorld(x,y,z,rotX,rotY,zoom)`：3D → 2D 透视投影
- `draw3DView()`：绘制 3D 预览（面片线框 + 参考图叠加 + 地面圆盘）
- `drawGroundDisk()`：绘制地面参考圆盘
- `init3DInteractions()`：鼠标拖拽旋转、滚轮缩放
- `S.showRefImage`：是否叠加参考图（可开关）

### 4.10 导出（约 3810-4100 行）
- `exportSVG()` / `exportJSON()` / `exportDXF()`：2D 曲线导出
- `exportOBJ()`：面片 OBJ 导出
- `exportCardFBX()`：**核心**——面片 FBX 导出（UE 可直接导入）
  - `formatFbxNum()`：FBX 数值格式化
- `exportCardOBJ()`：面片 OBJ 导出
- `downloadFile(name, content, mime)`：触发浏览器下载

### 4.11 输入模式与初始化（约 4100-4600 行）
- `switchInputMode(mode)`：单图/三视图切换
- `loadTriFile(view, file)`：加载单张三视图
- `guessTriView(filename)`：按文件名猜测视图（front/side/top 或 正/侧/顶）
- `batchLoadTri(files)`：批量拖拽载入（自动归位）
- `loadDemoImage()`：加载内置 demo 图（base64 内嵌）
- 三视图槽位的 click/dragover/drop 事件绑定

---

## 五、完整算法管线（extractAll 函数）

```
用户上传图
  │
  ├─ 1. 背景去除（可选，bgEnabled）
  │     estimateBackgroundColor → buildBackgroundMask
  │
  ├─ 2. 金色/亮色掩码
  │     extractGoldenMask（HSV + 亮度兜底）
  │     → canvasMask 显示
  │
  ├─ 3. 三视图融合（仅三视图模式）
  │     processTriViews（正面为主，侧/顶面补深度）
  │
  ├─ 4. 形态学固化
  │     solidifyMask（去小噪点 → close 填洞 → dilate 合并 → 去小噪点）
  │     → canvasSolid 显示
  │
  ├─ 5. 骨架化 + 修剪
  │     zhangSuen → pruneSkeleton
  │     → canvasSkeleton 显示
  │
  ├─ 6. 曲线追踪（traceMode = of/smart/angle）
  │     of: computeOrientationField → traceOrientationField → connectShortSegments
  │     → deduplicateCurves → classifyCurves
  │     → canvasCurves 显示
  │
  ├─ 7. 平滑
  │     rdpSimplify → bsplineInterpolate → smoothAllCurves
  │     每条曲线输出 800 个 C2 连续点
  │
  ├─ 8. 3D 面片生成
  │     buildCurveWorldPoints → buildFrames → buildCardMesh
  │     → draw3DView 预览
  │
  └─ 9. 导出（用户点击按钮）
        FBX / OBJ / JSON / SVG / DXF
```

---

## 六、关键参数（UI 左侧滑条）

| 参数 | ID | 默认值 | 说明 |
|------|-----|--------|------|
| 亮度阈值 | `brightThresh` | 0.45 | 掩码提取，越大只保留越亮的部分 |
| 色相范围 | `hueMin/hueMax` | 0.05/0.17 | 金色 HSV 色相 |
| 饱和度下限 | `satMin` | 0.25 | 金色饱和度 |
| 闭运算半径 | `closeRadius` | 5 | 形态学填洞，越大合并越强 |
| 膨胀半径 | `dilateRadius` | 1 | 合并邻近丝缕 |
| 最小对象 | `minObjectSize` | 800 | 去小连通块 |
| 修剪长度 | `pruneLength` | 25 | 骨架短毛刺修剪 |
| RDP 阈值 | `smoothEpsilon` | 8 | 曲线简化，越大越光滑 |
| 面片宽度 | `cardWidth` | 30 | 面片宽度（像素） |
| 面片数量 | `cardCount` | 2 | 1=单片, 2=十字, 3=三叶, 4=四叶 |
| 末端渐缩 | `cardTaper` | 0.3 | 面片末端宽度比例 |
| 最小曲线长度 | `minCurveLength` | 50 | 过滤过短曲线 |

---

## 七、Git 版本历史

完整 tag / 问题 / 修改见 **[VERSIONS.md](./VERSIONS.md)**。摘要：

- **v1.4**（`1a42f97`）：因 v1.2/v1.3 单图退化，算法回滚到 v1.1，保留三视图拖拽。
- **v1.4.1–v1.4.22**：在 v1.4 上做**线稿三视图**与光效图主干。当前线上目标 **v1.4.22**。
- 光效图（黑底金带）仍走方向场；白线黑底线稿走 `traceOrientationField` 惯性过交叉，**不要**对线稿做 B 样条。

---

## 八、已知问题（2026-09-01）

1. **三张手绘不是同一条空间线**：正视锁 XY 后，Z 不能同时贴侧视和俯视。用侧栏「信顶面」折中；要三张都准只能重画。详见 VERSIONS.md v1.4.19。
2. **线稿叠笔 + 交叉口**：自动可能漏笔或在 T 口拐错。用「点选补一笔」，已有的笔不要重复点。
3. **单图光效图仍可能要手调亮度阈值**（`brightThresh`）。
4. **精细模式 / 背景容差**对纯白线黑底线稿几乎无用。
5. **面片暂不做贴图**；3D 预览是 Canvas 自绘，曲线很多时会卡。
6. **本文第四节行号会过时**：用 Grep 搜函数名。

---

## 九、后续方向（用户可能要求的）

1. 线稿交叉口再稳（T 口 vs X 口）、点选补笔体验
2. 三视图笔画级对应（正/侧/顶各点一笔再拟合）
3. 从正+侧**生成**一致俯视，给画师当描图
4. 3D 预览里拖控制点；光带贴图到面片
5. UE 内导入插件、批量出 FBX

---

## 十、测试方法

### 手动测试
1. 浏览器打开 `app.html`
2. 点"加载示例"→ 点"提取曲线"→ 看各阶段预览（掩码/骨架/曲线/3D）
3. 切换"三视图识别"→ 拖入三张图 → 提取

### 自动化测试（input/run_tri.py）
```bash
cd H:\tool\curve-extractor\input
python run_tri.py g1   # 测试第一组三视图
python run_tri.py g2   # 测试第二组三视图
```
需要 Python + Playwright。脚本会自动加载 base64 素材、触发提取、截图保存。

### 验证标准
- demo 单图（光效）：应提出若干长曲线，面片居中于曲线
- 线稿三视图 group1（`processed_nolabel`）：约 3 根、无闭环；正视/侧视黄线贴墨（信顶面=0）；俯视对不齐是预期，把信顶面拖到 100% 俯视才应贴顶图
- Playwright：`python input/tri_labeled/debug/verify_overlay.py`（脚本在 gitignore 的 debug 目录，需本地有）

---

## 十一、部署与回滚

日常：

```bash
git checkout dev
git add app.html
git commit -m "v1.4.xx: 为什么改"
git push origin dev
```

上线（产品说「上线」之后）：

```bash
git checkout master
git merge dev
git push origin master
git checkout dev
```

GitHub Actions（`.github/workflows/pages.yml`）在 push `master` 后约 1–2 分钟更新 Pages。  
用户需 **Ctrl+F5** 强刷。

回滚某一版 `app.html`（推荐，不 force push）：

```bash
git checkout v1.4.19 -- app.html
git commit -m "rollback app.html to v1.4.19"
git push
```

---

## 十二、给下一个 Agent 的建议

1. **网页只改 `app.html`**。单文件是故意的。插件走 `blender_addon/`。
2. **提交推 `dev`，不要自行 merge `master`。**
3. 用 Grep 找函数，不要当行号还是 2026-08-30 那版。
4. 小步改、同一组 group1 三视图对比。线稿不要用三次 B 样条；平滑用 `fitSmoothPolyline`（拉普拉斯 + RDP + 向心 Catmull-Rom）。
5. 俯视对不齐先查「信顶面」再查几何；不要当成单纯 bug。
6. 用户 G 是产品经理；交付是特效师能进 UE 的 FBX。
7. 版本对不上就打开 **VERSIONS.md**。

---

*版本台账以 VERSIONS.md 为准。旧 Python 版在 archive/（gitignored）。*
