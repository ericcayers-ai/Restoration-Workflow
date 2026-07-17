"""Packaging preflight used by CI — no PyInstaller run required.

Validates that bundle_common declares InstructIR deps, legal notices exist,
and v0.6 packaged JSON data is importable.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PACKAGING_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGING_DIR.parent
REPO_ROOT = BACKEND_DIR.parent


def _literal_list(module: ast.Module, name: str) -> list[str]:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    value = ast.literal_eval(node.value)
                    if not isinstance(value, list):
                        raise TypeError(f"{name} is not a list")
                    return [str(v) for v in value]
    raise KeyError(name)


def main() -> int:
    errors: list[str] = []

    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        if not (REPO_ROOT / name).is_file():
            errors.append(f"missing {name} at repo root")

    data = BACKEND_DIR / "src" / "restoration" / "core" / "data"
    for name in ("rule_table.json", "instructir_prompts.json"):
        if not (data / name).is_file():
            errors.append(f"missing packaged data {name}")

    bundle_src_path = PACKAGING_DIR / "bundle_common.py"
    if not bundle_src_path.is_file():
        errors.append("missing bundle_common.py")
        collect: set[str] = set()
    else:
        bundle_src = bundle_src_path.read_text(encoding="utf-8")
        tree = ast.parse(bundle_src)
        try:
            collect = set(_literal_list(tree, "COLLECT_ALL"))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"could not parse COLLECT_ALL: {exc}")
            collect = set()
        if "LICENSE_BUNDLE" not in bundle_src or "THIRD_PARTY_NOTICES.md" not in bundle_src:
            errors.append("bundle_common.py does not stage LICENSE_BUNDLE / THIRD_PARTY_NOTICES.md")

    for pkg in ("transformers", "tokenizers", "torch", "safetensors"):
        if pkg not in collect:
            errors.append(f"COLLECT_ALL missing {pkg!r}")

    for script in (
        "build_exe.py",
        "make_windows_installer.py",
        "make_macos_dmg.py",
        "make_linux_appimage.py",
    ):
        if not (PACKAGING_DIR / script).is_file():
            errors.append(f"missing packaging script {script}")

    sys.path.insert(0, str(BACKEND_DIR / "src"))
    try:
        from restoration import API_VERSION, __version__
        from restoration.core.instruction import list_prompt_presets
        from restoration.nodes.instructir import InstructIrNode

        if __version__ != "0.6.1":
            errors.append(f"unexpected package version {__version__!r}")
        if not API_VERSION:
            errors.append("API_VERSION empty")
        if len(list_prompt_presets()) < 16:
            errors.append("InstructIR prompt library too small")
        names = {w.filename for w in InstructIrNode.weight_manifest}
        if "im_instructir-7d.pt" not in names:
            errors.append("InstructIR image weight missing from manifest")
        if not any(n.startswith("bge-micro-v2/") for n in names):
            errors.append("InstructIR text-encoder companions missing from manifest")
    except Exception as exc:  # noqa: BLE001 — report and fail
        errors.append(f"v0.6 import smoke failed: {exc}")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1
    print("packaging manifest OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
