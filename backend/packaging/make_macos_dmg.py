"""Wrap the macOS PyInstaller onedir in an unsigned .app + .dmg."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

import bundle_common  # noqa: E402


def _machine_tag() -> str:
    machine = os.uname().machine.lower() if hasattr(os, "uname") else "arm64"
    if machine in ("x86_64", "amd64"):
        return "macos-x64"
    return "macos-arm64"


def build_app_bundle(app_dir: Path, staging: Path) -> Path:
    """Create ``Restoration Workflow.app`` containing the onedir payload."""
    binary = app_dir / "RestorationWorkflow"
    if not binary.is_file():
        raise FileNotFoundError(f"missing macOS binary: {binary}")

    app_name = f"{bundle_common.APP_DISPLAY_NAME}.app"
    app_path = staging / app_name
    if app_path.exists():
        shutil.rmtree(app_path)

    contents = app_path / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    payload = resources / "RestorationWorkflow"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)

    shutil.copytree(app_dir, payload, symlinks=True)

    launcher = macos / "RestorationWorkflow"
    launcher.write_text(
        "#!/bin/bash\n"
        'DIR="$(cd "$(dirname "$0")/../Resources/RestorationWorkflow" && pwd)"\n'
        'cd "$DIR" || exit 1\n'
        'exec "$DIR/RestorationWorkflow" "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    launcher.chmod(0o755)
    (payload / "RestorationWorkflow").chmod(0o755)

    icon = bundle_common.ensure_icon_png(resources / "AppIcon.png")
    info = {
        "CFBundleName": bundle_common.APP_DISPLAY_NAME,
        "CFBundleDisplayName": bundle_common.APP_DISPLAY_NAME,
        "CFBundleIdentifier": bundle_common.APP_IDENTIFIER,
        "CFBundleVersion": bundle_common.APP_VERSION,
        "CFBundleShortVersionString": bundle_common.APP_VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "RestorationWorkflow",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)

    # Keep icon path referenced for future icns conversion; PNG is enough for now.
    _ = icon
    return app_path


def build_macos_dmg(app_dir: Path, dist_dir: Path) -> Path:
    """Produce an unsigned UDZO DMG with the .app and an Applications link."""
    version = bundle_common.APP_VERSION
    tag = _machine_tag()
    dmg_name = f"RestorationWorkflow-{version}-{tag}.dmg"
    dmg_path = dist_dir / dmg_name
    if dmg_path.exists():
        dmg_path.unlink()

    dist_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rw-dmg-") as tmp:
        staging = Path(tmp) / "dmg"
        staging.mkdir()
        app_path = build_app_bundle(app_dir, staging)
        applications = staging / "Applications"
        applications.symlink_to("/Applications")

        # Brief first-run note (Gatekeeper).
        (staging / "README-macOS.txt").write_text(
            "Restoration Workflow for macOS\n"
            "==============================\n\n"
            "1. Drag Restoration Workflow.app to Applications.\n"
            "2. First launch: right-click the app → Open (unsigned build).\n"
            "   Or: xattr -cr \"/Applications/Restoration Workflow.app\"\n\n"
            "The app starts a local server and opens your browser.\n"
            "No Python install required. GPU optional.\n",
            encoding="utf-8",
            newline="\n",
        )

        cmd = [
            "hdiutil",
            "create",
            "-volname",
            bundle_common.APP_DISPLAY_NAME,
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]
        print("Creating DMG:\n  " + " ".join(cmd))
        subprocess.run(cmd, check=True)
        _ = app_path

    if not dmg_path.is_file():
        raise FileNotFoundError(f"DMG not produced: {dmg_path}")
    return dmg_path


def main() -> int:
    try:
        bundle_common.run_pyinstaller()
        path = build_macos_dmg(bundle_common.APP_DIR, bundle_common.DIST_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"macOS DMG: {path} ({path.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
