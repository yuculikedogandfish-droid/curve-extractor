# Curve Extractor — Blender 插件

从 HTML 工具导出的 `curves.json`（v1.4.19+，含 `points3d`）导入 3D 曲线，并按同样参数生成交叉面片。

发给同事用压缩包：`release/CurveExtractor-v1.4.19-Blender.zip`（zip 根目录必须是 `curve_extractor/` 文件夹）。

重新打包（在仓库根目录）：

```powershell
Compress-Archive -Path blender_addon\curve_extractor -DestinationPath release\CurveExtractor-v1.4.19-Blender.zip -Force
```

安装：Blender → Preferences → Add-ons → Install，选该 zip，启用后在 3D 视图 N 面板「Curve Extractor」。
