# Write a Houdini package file that points at this folder.
# Run once after unzipping. Internal distribution only.

from __future__ import annotations

import json
import sys
from pathlib import Path


def houdini_user_dirs():
    home = Path.home()
    docs = home / "Documents"
    found = []
    for root in (docs, home):
        if not root.is_dir():
            continue
        for child in root.iterdir():
            name = child.name.lower()
            if child.is_dir() and name.startswith("houdini"):
                found.append(child)
    return sorted(found)


def main():
    root = Path(__file__).resolve().parent
    targets = houdini_user_dirs()
    if not targets:
        print("未找到 Houdini 用户目录（Documents/houdiniXX.X）。")
        print("请把 packages/curve_extractor.json 手动拷到对应 packages 文件夹，")
        print("并把 JSON 里的路径改成：")
        print("  ", root)
        return 1
    payload = {
        "load_package_once": True,
        "enable": True,
        "env": [
            {"CURVE_EXTRACTOR": str(root).replace("\\", "/")},
            {
                "PYTHONPATH": {
                    "method": "prepend",
                    "value": "$CURVE_EXTRACTOR/python",
                }
            },
            {
                "HOUDINI_TOOLBAR_PATH": {
                    "method": "prepend",
                    "value": "$CURVE_EXTRACTOR/toolbar",
                }
            },
        ],
    }
    written = []
    for user_dir in targets:
        pkg_dir = user_dir / "packages"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        dest = pkg_dir / "curve_extractor.json"
        dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append(dest)
    print("已写入：")
    for p in written:
        print(" ", p)
    print("重启 Houdini 后，在 Shelf 里加 Tab「Curve Extractor」。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
