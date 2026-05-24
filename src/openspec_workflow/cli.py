from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from openspec_workflow.archive import ArchivePreflightError, archive_preflight
from openspec_workflow.explainer import ExplainerGenerationError, generate_explainer
from openspec_workflow.manifest import build_manifest, write_manifest
from openspec_workflow.policy import PolicyError, load_policy, resolve_change_dir
from openspec_workflow.scaffold import ScaffoldError, scaffold_change
from openspec_workflow.validation import validate_explainer_artifact, validate_source_manifest


def _project_root(raw: str | None) -> Path:
    return Path(raw or ".").resolve()


def _policy(project_root: Path, raw_path: str | None):
    path = Path(raw_path).resolve() if raw_path else None
    return load_policy(project_root, path)


def _dump(data: dict[str, Any], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            print(f"{key}={json.dumps(value, ensure_ascii=False)}")
        else:
            print(f"{key}={value}")


def cmd_propose(args: argparse.Namespace) -> int:
    project_root = _project_root(args.project_root)
    try:
        policy = _policy(project_root, args.policy)
        change_dir = scaffold_change(
            project_root,
            policy,
            args.change_name,
            force=args.force,
            with_manifest=not args.no_manifest,
        )
        generated = None
        if not args.skip_explainer and policy.change_explainer.required:
            generated = generate_explainer(args.change_name, change_dir, policy, backend=args.backend)
    except (PolicyError, ScaffoldError, ExplainerGenerationError) as err:
        _dump({"status": "fail", "error": str(err)}, args.json)
        return 1

    result = {
        "status": "ok",
        "changeName": args.change_name,
        "changeDir": str(change_dir),
        "manifest": str(change_dir / "source-manifest.json") if not args.no_manifest else "skipped",
        "explainer": str(generated) if generated else "skipped",
    }
    _dump(result, args.json)
    return 0


def cmd_build_source_manifest(args: argparse.Namespace) -> int:
    project_root = _project_root(args.project_root)
    try:
        policy = _policy(project_root, args.policy)
        change_dir = resolve_change_dir(project_root, policy, args.change_name)
        if not change_dir.exists():
            raise FileNotFoundError(f"Change directory not found: {change_dir}")
        manifest = build_manifest(args.change_name, change_dir)
        output = write_manifest(change_dir, manifest)
    except (PolicyError, FileNotFoundError) as err:
        _dump({"status": "fail", "error": str(err)}, args.json)
        return 1
    _dump({"status": "ok", "output": str(output)}, args.json)
    return 0


def cmd_generate_explainer(args: argparse.Namespace) -> int:
    project_root = _project_root(args.project_root)
    try:
        policy = _policy(project_root, args.policy)
        change_dir = resolve_change_dir(project_root, policy, args.change_name)
        output = generate_explainer(args.change_name, change_dir, policy, backend=args.backend)
    except (PolicyError, ExplainerGenerationError) as err:
        _dump({"status": "fail", "error": str(err)}, args.json)
        return 1
    _dump({"status": "ok", "output": str(output)}, args.json)
    return 0


def cmd_validate_explainer(args: argparse.Namespace) -> int:
    project_root = _project_root(args.project_root)
    try:
        policy = _policy(project_root, args.policy)
        change_dir = resolve_change_dir(project_root, policy, args.change_name)
        artifact = validate_explainer_artifact(args.change_name, change_dir, policy)
    except PolicyError as err:
        _dump({"status": "fail", "error": str(err)}, args.json)
        return 1
    result = {"status": artifact.status, **artifact.data}
    _dump(result, args.json)
    return 0 if artifact.status == "ok" else 1


def cmd_validate_source_manifest(args: argparse.Namespace) -> int:
    project_root = _project_root(args.project_root)
    try:
        policy = _policy(project_root, args.policy)
        change_dir = resolve_change_dir(project_root, policy, args.change_name)
        result = validate_source_manifest(args.change_name, change_dir)
    except PolicyError as err:
        _dump({"status": "fail", "error": str(err)}, args.json)
        return 1
    payload = {"status": result.status, **result.data}
    _dump(payload, args.json)
    return 0 if result.status in {"ok", "not_present"} else 1


def cmd_archive_preflight(args: argparse.Namespace) -> int:
    project_root = _project_root(args.project_root)
    try:
        policy = _policy(project_root, args.policy)
        report = archive_preflight(project_root, policy, args.change_name)
    except (PolicyError, ArchivePreflightError) as err:
        _dump({"status": "fail", "error": str(err)}, args.json)
        return 1
    _dump(report, args.json)
    return 0 if report.get("status") == "ok" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Harness-neutral OpenSpec workflow core")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", help="target project root", default=".")
    common.add_argument("--policy", help="explicit policy file path")

    propose = subparsers.add_parser("propose", parents=[common])
    propose.add_argument("change_name")
    propose.add_argument("--force", action="store_true")
    propose.add_argument("--no-manifest", action="store_true")
    propose.add_argument("--skip-explainer", action="store_true")
    propose.add_argument("--backend", choices=["template", "opendesign"])
    propose.set_defaults(func=cmd_propose)

    manifest = subparsers.add_parser("build-source-manifest", parents=[common])
    manifest.add_argument("change_name")
    manifest.set_defaults(func=cmd_build_source_manifest)

    gen = subparsers.add_parser("generate-explainer", parents=[common])
    gen.add_argument("change_name")
    gen.add_argument("--backend", choices=["template", "opendesign"])
    gen.set_defaults(func=cmd_generate_explainer)

    validate = subparsers.add_parser("validate-explainer", parents=[common])
    validate.add_argument("change_name")
    validate.set_defaults(func=cmd_validate_explainer)

    validate_manifest = subparsers.add_parser("validate-source-manifest", parents=[common])
    validate_manifest.add_argument("change_name")
    validate_manifest.set_defaults(func=cmd_validate_source_manifest)

    archive = subparsers.add_parser("archive-preflight", parents=[common])
    archive.add_argument("change_name")
    archive.set_defaults(func=cmd_archive_preflight)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))
