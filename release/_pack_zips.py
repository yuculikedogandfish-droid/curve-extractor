"""Pack DCC zips with forward-slash paths. Do not commit the zips."""
from __future__ import annotations

from pathlib import Path
import zipfile

ROOT = Path(r"h:\tool\curve-extractor")
REL = ROOT / "release"
REL.mkdir(parents=True, exist_ok=True)

SKIP = {"__pycache__", ".pyc"}


def should_skip(p: Path) -> bool:
    return any(part == "__pycache__" or part.endswith(".pyc") for part in p.parts)


def pack(src: Path, dest: Path, prefix: str, rel_root: Path) -> None:
    if dest.exists():
        dest.unlink()
    n = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if not p.is_file() or should_skip(p):
                continue
            arc = Path(prefix) / p.relative_to(rel_root)
            zf.write(p, arc.as_posix())
            n += 1
    print("wrote", dest.name, n, "files", dest.stat().st_size)


def main():
    pack(
        ROOT / "blender_addon" / "curve_extractor",
        REL / "CurveExtractor-v1.4.26-Blender.zip",
        "curve_extractor",
        ROOT / "blender_addon" / "curve_extractor",
    )
    pack(
        ROOT / "houdini_addon",
        REL / "CurveExtractor-v1.4.26-Houdini.zip",
        "CurveExtractor-Houdini",
        ROOT / "houdini_addon",
    )


if __name__ == "__main__":
    main()
