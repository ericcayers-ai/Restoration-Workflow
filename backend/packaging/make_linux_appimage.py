"""Wrap the Linux PyInstaller onedir in an AppImage."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

import bundle_common  # noqa: E402

APPIMAGETOOL_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/"
    "continuous/appimagetool-x86_64.AppImage"
)


def _ensure_appimagetool(cache_dir: Path) -> Path:
    env = os.environ.get("APPIMAGETOOL")
    if env and Path(env).is_file():
        return Path(env)
    which = shutil.which("appimagetool")
    if which:
        return Path(which)

    cache_dir.mkdir(parents=True, exist_ok=True)
    tool = cache_dir / "appimagetool-x86_64.AppImage"
    if not tool.is_file():
        print(f"Downloading appimagetool → {tool}")
        urllib.request.urlretrieve(APPIMAGETOOL_URL, tool)  # noqa: S310 — fixed URL
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return tool


def build_linux_appimage(app_dir: Path, dist_dir: Path) -> Path:
    """Produce ``RestorationWorkflow-<ver>-linux-x86_64.AppImage``."""
    binary = app_dir / "RestorationWorkflow"
    if not binary.is_file():
        raise FileNotFoundError(f"missing Linux binary: {binary}")

    version = bundle_common.APP_VERSION
    out_name = f"RestorationWorkflow-{version}-linux-x86_64.AppImage"
    out_path = dist_dir / out_name
    if out_path.exists():
        out_path.unlink()

    dist_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rw-appimage-") as tmp:
        appdir = Path(tmp) / "RestorationWorkflow.AppDir"
        payload = appdir / "usr" / "lib" / "RestorationWorkflow"
        appdir.mkdir(parents=True)
        shutil.copytree(app_dir, payload, symlinks=True)
        (payload / "RestorationWorkflow").chmod(0o755)

        icon = bundle_common.ensure_icon_png(appdir / "restoration-workflow.png")
        # Also place icon where some desktops look.
        shutil.copy2(icon, appdir / ".DirIcon")

        desktop = appdir / "restoration-workflow.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={bundle_common.APP_DISPLAY_NAME}\n"
            "Comment=Photo restoration workflow (local server + browser UI)\n"
            "Exec=AppRun\n"
            "Icon=restoration-workflow\n"
            "Categories=Graphics;Photography;\n"
            "Terminal=false\n",
            encoding="utf-8",
            newline="\n",
        )

        apprun = appdir / "AppRun"
        apprun.write_text(
            "#!/bin/bash\n"
            'HERE="$(dirname "$(readlink -f "$0")")"\n'
            'DIR="$HERE/usr/lib/RestorationWorkflow"\n'
            'cd "$DIR" || exit 1\n'
            'exec "$DIR/RestorationWorkflow" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        apprun.chmod(0o755)

        tool = _ensure_appimagetool(Path(tmp) / "tools")
        env = os.environ.copy()
        env.setdefault("ARCH", "x86_64")
        # Unsigned AppImage is expected for OSS without a signing key.
        env.setdefault("APPIMAGE_EXTRACT_AND_RUN", "1")
        cmd = [str(tool), "--no-appstream", str(appdir), str(out_path)]
        print("Running appimagetool:\n  " + " ".join(cmd))
        subprocess.run(cmd, check=True, env=env)

    if not out_path.is_file():
        raise FileNotFoundError(f"AppImage not produced: {out_path}")
    out_path.chmod(out_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return out_path


def main() -> int:
    try:
        bundle_common.run_pyinstaller()
        path = build_linux_appimage(bundle_common.APP_DIR, bundle_common.DIST_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Linux AppImage: {path} ({path.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
