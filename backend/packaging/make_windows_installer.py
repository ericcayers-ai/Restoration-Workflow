"""Wrap the Windows PyInstaller onedir in an Inno Setup installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

import bundle_common  # noqa: E402

ISS_TEMPLATE = """; Restoration Workflow — Inno Setup script (generated)
#define MyAppVersion "{version}"
#define SourceDir "{source_dir}"
#define OutputDir "{output_dir}"
#define OutputBase "{output_base}"

[Setup]
AppId={{{{A7C3E91B-4F2D-4B8A-9E1C-6D8F0A2B4C61}}}}
AppName=Restoration Workflow
AppVersion={{#MyAppVersion}}
AppPublisher=Eric Cayers
AppPublisherURL=https://github.com/ericcayers-ai/Restoration-Workflow
AppSupportURL=https://github.com/ericcayers-ai/Restoration-Workflow/issues
DefaultDirName={{autopf}}\\Restoration Workflow
DefaultGroupName=Restoration Workflow
DisableProgramGroupPage=yes
LicenseFile={{#SourceDir}}\\LICENSE
InfoBeforeFile={{#SourceDir}}\\README.txt
OutputDir={{#OutputDir}}
OutputBaseFilename={{#OutputBase}}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Restoration Workflow
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{{#SourceDir}}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\Restoration Workflow"; Filename: "{{app}}\\RestorationWorkflow.exe"; WorkingDir: "{{app}}"
Name: "{{group}}\\Uninstall Restoration Workflow"; Filename: "{{uninstallexe}}"
Name: "{{autodesktop}}\\Restoration Workflow"; Filename: "{{app}}\\RestorationWorkflow.exe"; WorkingDir: "{{app}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\RestorationWorkflow.exe"; Description: "Launch Restoration Workflow"; Flags: nowait postinstall skipifsilent
"""


def _find_iscc() -> Path | None:
    env = os.environ.get("INNO_SETUP_ISCC")
    if env:
        p = Path(env)
        if p.is_file():
            return p
    which = shutil.which("iscc") or shutil.which("ISCC.exe")
    if which:
        return Path(which)
    for candidate in (
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ):
        if candidate.is_file():
            return candidate
    return None


def build_windows_installer(app_dir: Path, dist_dir: Path) -> Path:
    """Compile an Inno Setup installer from the onedir at ``app_dir``."""
    exe = app_dir / "RestorationWorkflow.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"missing Windows exe: {exe}")

    version = bundle_common.APP_VERSION
    output_base = f"RestorationWorkflow-Setup-{version}-windows-x64"
    out_path = dist_dir / f"{output_base}.exe"
    if out_path.exists():
        out_path.unlink()

    iscc = _find_iscc()
    if iscc is None:
        raise FileNotFoundError(
            "Inno Setup compiler (ISCC.exe) not found. "
            "Install Inno Setup 6 or set INNO_SETUP_ISCC."
        )

    # Ensure README exists for InfoBeforeFile (installer stages one if missing).
    readme = app_dir / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "Restoration Workflow\n"
            "====================\n\n"
            "After install, launch from the Start Menu.\n"
            "The app starts a local server and opens your browser.\n",
            encoding="utf-8",
        )

    # Inno accepts forward slashes; avoids escape issues in #define strings.
    source_dir = str(app_dir.resolve()).replace("\\", "/")
    output_dir = str(dist_dir.resolve()).replace("\\", "/")
    iss_text = ISS_TEMPLATE.format(
        version=version,
        source_dir=source_dir,
        output_dir=output_dir,
        output_base=output_base,
    )

    dist_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rw-inno-") as tmp:
        iss_path = Path(tmp) / "installer.iss"
        iss_path.write_text(iss_text, encoding="utf-8")
        cmd = [str(iscc), str(iss_path)]
        print("Running Inno Setup:\n  " + " ".join(cmd))
        subprocess.run(cmd, check=True)

    if not out_path.is_file():
        raise FileNotFoundError(f"Inno Setup did not produce {out_path}")
    return out_path


def main() -> int:
    try:
        path = build_windows_installer(bundle_common.APP_DIR, bundle_common.DIST_DIR)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
