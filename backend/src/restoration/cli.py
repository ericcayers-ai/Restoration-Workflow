"""``restore`` — the terminal surface over the same engine the API drives.

Phase 1's acceptance criterion lives here: ``restore run`` has to take a real
photo through a real pipeline from a cold terminal, on a CUDA box and on a
CPU-only box, with the CPU path degrading rather than erroring. Batch and
automation are first-class (ARCHITECTURE.md section 7), so ``--input`` accepts a
directory as readily as a file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .core.errors import RestorationError
from .core.executor import PipelineSpec, parse_pipeline
from .core.images import is_supported_image, load_image, save_image
from .core.types import NodeStatus, ProgressEvent
from .presets import load_preset_file
from .service import AppServices


def _eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"  # pragma: no cover


def _build_services(args: argparse.Namespace) -> AppServices:
    return AppServices(
        data_dir=Path(args.data_dir) if getattr(args, "data_dir", None) else None,
        force_cpu=True if getattr(args, "cpu", False) else None,
    )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _resolve_pipeline(
    services: AppServices, args: argparse.Namespace, image: Any
) -> tuple[PipelineSpec, dict[str, Any] | None]:
    if args.pipeline:
        document = json.loads(Path(args.pipeline).read_text("utf-8"))
        return parse_pipeline(document, services.registry), None
    if args.preset:
        candidate = Path(args.preset)
        preset = (
            load_preset_file(candidate)
            if candidate.exists()
            else services.presets.get(args.preset)
        )
        return parse_pipeline(preset.pipeline, services.registry), None
    if getattr(args, "instructir_preset", None):
        plan = services.build_ensemble(
            image,
            prompt_preset_id=args.instructir_preset,
            mode="guide_and_finish",
        )
        return parse_pipeline(plan["pipeline"], services.registry), {
            "profile": services.analyzer.analyze(image).to_dict(),
            "routing": {
                "chain": plan["chain"],
                "params": plan["params"],
                "reasons": plan["reasons"],
            },
            "master_instruction": plan["instruction"],
        }

    from .core.quality import QualityTier  # noqa: PLC0415

    tier = QualityTier(getattr(args, "quality", None) or "balanced")
    auto = services.analyze(image, tier)
    return auto.spec, auto.to_dict()


def _print_routing(analysis: dict[str, Any]) -> None:
    profile = analysis["profile"]
    _eprint(
        f"  analyzed: {profile['width']}x{profile['height']} "
        f"blur={profile['blur_score']:.0f} noise={profile['noise_score']:.4f} "
        f"jpeg={profile['jpeg_blockiness']:.3f} faces={profile['face_count']}"
    )
    for reason in analysis["routing"]["reasons"]:
        _eprint(f"  -> {reason['node']}: {reason['reason']}")


def _progress_printer(quiet: bool):
    seen: set[tuple[str, str]] = set()

    def emit(event: ProgressEvent) -> None:
        if quiet:
            return
        key = (event.node_id, event.status.value)
        if event.status in (NodeStatus.RUNNING, NodeStatus.QUEUED) and key in seen:
            return
        seen.add(key)
        if event.status is NodeStatus.QUEUED:
            return
        suffix = " (cached)" if event.cached else ""
        message = f": {event.message}" if event.message else ""
        _eprint(f"  [{event.node_id}] {event.status.value}{suffix}{message}")

    return emit


async def _run_one(
    services: AppServices,
    args: argparse.Namespace,
    source: Path,
    out_dir: Path,
) -> Path:
    image = load_image(source)
    spec, analysis = _resolve_pipeline(services, args, image)

    _eprint(f"{source.name}: {' -> '.join(n.type for n in spec.nodes)}")
    if analysis and not args.quiet:
        _print_routing(analysis)

    missing = services.missing_weights(spec)
    if missing:
        if not args.download:
            raise SystemExit(
                f"weights not installed for: {', '.join(missing)}\n"
                f"install them with: restore weights download {missing[0]}\n"
                f"or re-run with --download to fetch them now"
            )
        for node_id in missing:
            _download(services, node_id, accept_license=args.accept_license)

    result = await services.executor.execute(
        spec, image, job_id=source.stem, emit=_progress_printer(args.quiet)
    )
    destination = out_dir / f"{source.stem}.png"
    save_image(result, destination)
    _eprint(f"  wrote {destination}")
    return destination


def cmd_run(args: argparse.Namespace) -> int:
    services = _build_services(args)
    source = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if source.is_dir():
        sources = sorted(p for p in source.iterdir() if p.is_file() and is_supported_image(p))
        if not sources:
            _eprint(f"no supported images in {source}")
            return 1
    elif source.is_file():
        sources = [source]
    else:
        _eprint(f"no such file or directory: {source}")
        return 1

    info = services.hardware.detect()
    gpu_name = f" ({info.devices[0].name})" if info.devices else ""
    _eprint(f"device: {info.device_string}{gpu_name}")

    failures = 0
    for path in sources:
        try:
            asyncio.run(_run_one(services, args, path, out_dir))
        except RestorationError as exc:
            failures += 1
            _eprint(f"  error: {exc}")
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# analyze / nodes / hardware
# ---------------------------------------------------------------------------

def cmd_analyze(args: argparse.Namespace) -> int:
    from .core.quality import QualityTier  # noqa: PLC0415

    services = _build_services(args)
    tier = QualityTier(getattr(args, "quality", None) or "balanced")
    auto = services.analyze(load_image(Path(args.input)), tier)
    payload = auto.to_dict()
    payload["missing_weights"] = services.missing_weights(auto.spec)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{args.input}")
    _print_routing(payload)
    print(f"pipeline: {' -> '.join(n.type for n in auto.spec.nodes)}")
    if payload["missing_weights"]:
        print(f"missing weights: {', '.join(payload['missing_weights'])}")
    return 0


def cmd_nodes(args: argparse.Namespace) -> int:
    services = _build_services(args)
    described = services.describe_nodes()
    if args.json:
        print(json.dumps(described, indent=2))
        return 0

    for node in described:
        availability = node["availability"]
        mark = "ok " if availability["state"] != "unavailable" else "-- "
        badge = f" [{availability['badge']}]" if availability["badge"] else ""
        installed = "installed" if node["weights"]["installed"] else "not installed"
        print(f"{mark}{node['id']:<18} {node['category']:<14} {node['vram_tier']:<10} "
              f"{node['license']['spdx_id']:<14} {installed}{badge}")
        if availability["reason"]:
            print(f"     {availability['reason']}")
    if services.registry.plugin_errors:
        print("\nplugin load errors:")
        for error in services.registry.plugin_errors:
            print(f"  {error['plugin']}: {error['error']}")
    return 0


def cmd_hardware(args: argparse.Namespace) -> int:
    services = _build_services(args)
    info = services.hardware.detect()
    if args.json:
        print(json.dumps(info.to_dict(), indent=2))
        return 0
    print(f"backend:       {info.backend}")
    print(f"torch:         {info.torch_version or 'not installed'}")
    for device in info.devices:
        print(f"gpu {device.index}:         {device.name} ({device.total_vram_mb}MB)")
    if not info.devices:
        print("gpu:           none detected (CPU-only; LOW-tier nodes still run)")
    return 0


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------

def _download(services: AppServices, node_id: str, *, accept_license: bool) -> None:
    node = services.registry.create(node_id)
    if node.license.requires_acknowledgement and not services.weights.is_acknowledged(node_id):
        _eprint(
            f"\n'{node_id}' is licensed {node.license.spdx_id} "
            f"({node.license.kind.value}).\n"
            f"  {node.license.source_url}\n"
            f"This is not a permissive licence. Review it before downloading."
        )
        if not accept_license:
            raise SystemExit(
                f"refusing to download '{node_id}' without an explicit licence "
                f"acknowledgement; re-run with --accept-license once you have read it"
            )
        services.weights.acknowledge_license(node)
        _eprint(f"  recorded licence acknowledgement for '{node_id}'")

    total = sum(
        w.size_bytes for w in services.weights.required_files(node)
        if not services.weights.file_path(node.id, w).exists()
    )
    if total <= 0:
        total = sum(w.size_bytes for w in services.weights.required_files(node))
    _eprint(f"downloading {node_id} ({_human_bytes(total)})")

    last = [""]

    def on_progress(filename: str, done: int, size: int) -> None:
        if filename != last[0]:
            last[0] = filename
            _eprint(f"  {filename}")
        pct = (done / size * 100) if size else 0.0
        print(f"\r    {_human_bytes(done)}/{_human_bytes(size)} ({pct:.0f}%)",
              end="", file=sys.stderr, flush=True)

    services.weights.download(node, on_progress)
    _eprint("")


def cmd_weights(args: argparse.Namespace) -> int:
    services = _build_services(args)

    if args.weights_command == "list":
        for node in services.registry.all_nodes():
            if not node.weight_manifest:
                continue
            status = services.weights.status(node)
            mark = "installed    " if status.installed else "not installed"
            gate = "" if status.acknowledged else "  (licence acknowledgement required)"
            print(f"{mark} {node.id:<18} {_human_bytes(status.total_size_bytes):>8}{gate}")
        print(f"\ncache: {services.weights.root}")
        return 0

    if args.weights_command == "download":
        _download(services, args.node_id, accept_license=args.accept_license)
        print(f"{args.node_id}: installed")
        return 0

    if args.weights_command == "remove":
        removed = services.weights.remove(args.node_id)
        print(f"{args.node_id}: {'removed' if removed else 'nothing to remove'}")
        return 0

    return 1  # pragma: no cover - argparse enforces the choices


# ---------------------------------------------------------------------------
# presets / plugins / serve
# ---------------------------------------------------------------------------

def cmd_presets(args: argparse.Namespace) -> int:
    services = _build_services(args)
    presets = services.presets.list()
    if not presets:
        print(f"no presets in {services.presets.root}")
        return 0
    for preset in presets:
        chain = " -> ".join(n.get("type", "?") for n in preset.pipeline.get("nodes", []))
        print(f"{preset.name:<24} {chain}")
        if preset.description:
            print(f"  {preset.description}")
    return 0


def cmd_plugin(args: argparse.Namespace) -> int:
    from .nodes import BUILTIN_NODES  # noqa: PLC0415

    services = _build_services(args)
    builtin = {cls.id for cls in BUILTIN_NODES}
    print(f"plugins directory: {services.plugins_dir}")
    third_party = [n for n in services.registry.ids() if n not in builtin]
    for node_id in third_party:
        print(f"  {node_id}")
    if not third_party:
        print("  (none installed)")
    for error in services.registry.plugin_errors:
        print(f"  ! {error['plugin']}: {error['error']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn  # noqa: PLC0415

    from .api import create_app  # noqa: PLC0415

    services = _build_services(args)
    app = create_app(services)
    if app.state.frontend_mounted:
        _eprint(f"serving app + API at http://{args.host}:{args.port}")
    else:
        _eprint(
            f"serving API only at http://{args.host}:{args.port} "
            f"(no frontend build found; run 'npm run build' in frontend/, "
            f"or point RESTORE_FRONTEND_DIST at one)"
        )
    # Port 0 lets the OS pick a free one; bound to loopback only, never 0.0.0.0
    # (ARCHITECTURE.md section 1).
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="restore", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"restore {__version__}")
    parser.add_argument("--data-dir", help="override the app data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="restore an image or a folder of images")
    run.add_argument("--input", "-i", required=True, help="image file or directory")
    run.add_argument("--output", "-o", required=True, help="output directory")
    group = run.add_mutually_exclusive_group()
    group.add_argument("--preset", help="preset name or path to a preset JSON file")
    group.add_argument("--pipeline", help="path to a pipeline JSON file")
    group.add_argument(
        "--instructir-preset",
        dest="instructir_preset",
        help="Master Restorer prompt id — build a guided specialist ensemble",
    )
    run.add_argument("--download", action="store_true", help="fetch missing weights first")
    run.add_argument("--accept-license", action="store_true",
                     help="record acknowledgement for non-permissive licences")
    run.add_argument("--cpu", action="store_true", help="force CPU even if a GPU is present")
    run.add_argument(
        "--quality", choices=["draft", "balanced", "high"], default="balanced",
        help="speed/quality tradeoff for the automatic pipeline (ignored with "
             "--pipeline/--preset, which already say exactly what to run)",
    )
    run.add_argument("--quiet", "-q", action="store_true")
    run.set_defaults(func=cmd_run)

    analyze = sub.add_parser("analyze", help="show the degradation profile and chosen pipeline")
    analyze.add_argument("--input", "-i", required=True)
    analyze.add_argument("--json", action="store_true")
    analyze.add_argument("--cpu", action="store_true")
    analyze.add_argument("--quality", choices=["draft", "balanced", "high"], default="balanced")
    analyze.set_defaults(func=cmd_analyze)

    nodes = sub.add_parser("nodes", help="list registered nodes and their availability")
    nodes.add_argument("--json", action="store_true")
    nodes.add_argument("--cpu", action="store_true")
    nodes.set_defaults(func=cmd_nodes)

    hardware = sub.add_parser("hardware", help="show detected compute backend")
    hardware.add_argument("--json", action="store_true")
    hardware.add_argument("--cpu", action="store_true")
    hardware.set_defaults(func=cmd_hardware)

    weights = sub.add_parser("weights", help="manage model weights")
    weights_sub = weights.add_subparsers(dest="weights_command", required=True)
    weights_sub.add_parser("list", help="list weight install state")
    download = weights_sub.add_parser("download", help="download a node's weights")
    download.add_argument("node_id")
    download.add_argument("--accept-license", action="store_true")
    remove = weights_sub.add_parser("remove", help="delete a node's weights")
    remove.add_argument("node_id")
    weights.set_defaults(func=cmd_weights, accept_license=False)

    presets = sub.add_parser("presets", help="list saved presets")
    presets.set_defaults(func=cmd_presets)

    plugin = sub.add_parser("plugin", help="plugin diagnostics")
    plugin_sub = plugin.add_subparsers(dest="plugin_command", required=True)
    plugin_sub.add_parser("list", help="list discovered third-party nodes")
    plugin.set_defaults(func=cmd_plugin)

    serve = sub.add_parser("serve", help="run the backend API (headless server mode)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--log-level", default="info")
    serve.add_argument("--cpu", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def _force_utf8_output() -> None:
    """Windows consoles still default to a legacy code page, which mangles the
    em-dashes in the rule table's human-readable reasons. Reconfigure rather
    than restrict what the data file is allowed to contain."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - detached stream
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except SystemExit as exc:
        if exc.code not in (0, None):
            _eprint(str(exc))
        return int(exc.code or 0) if isinstance(exc.code, int) else 1
    except RestorationError as exc:
        _eprint(f"error: {exc}")
        fallback = getattr(exc, "fallback", None)
        if fallback:
            _eprint(f"hint: {fallback}")
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        _eprint("interrupted")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
