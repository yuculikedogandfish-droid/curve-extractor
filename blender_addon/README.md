# Curve Extractor — Blender 插件

从 HTML 工具导出的 `curves.json`（v1.4.19+，含 `points3d`）导入 3D 曲线，并按同样参数生成交叉面片。

发给同事用压缩包：`release/CurveExtractor-v1.4.22-Blender.zip`（zip 根目录必须是 `curve_extractor/` 文件夹，路径一律正斜杠）。

重新打包（在仓库根目录，用 Python，不要用 PowerShell `Compress-Archive`，那会把反斜杠写进 zip）：

```powershell
python -c "from pathlib import Path; import zipfile; root=Path('blender_addon/curve_extractor'); out=Path('release/CurveExtractor-v1.4.22-Blender.zip'); z=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED); [z.write(f, arcname='curve_extractor/'+f.relative_to(root).as_posix()) for f in root.rglob('*') if f.is_file() and '__pycache__' not in f.parts]; z.close()"
```

安装：Blender → Preferences → Add-ons → Install，选该 zip，启用后在 3D 视图 N 面板「Curve Extractor」。
