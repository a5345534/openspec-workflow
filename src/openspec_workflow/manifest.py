from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "1.0"
SOURCE_CANDIDATES = (
    ("proposal.md", "proposal"),
    ("design.md", "design"),
    ("tasks.md", "tasks"),
)


def load_json(path: Path) -> Any:
    with path.open() as handle:
        return json.load(handle)


def sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detect_sources(change_dir: Path) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    for rel, kind in SOURCE_CANDIDATES:
        path = change_dir / rel
        if path.exists():
            sources.append({"path": rel, "kind": kind, "sha256": sha256_text(path)})

    specs_dir = change_dir / "specs"
    if specs_dir.exists():
        for spec_path in sorted(specs_dir.rglob("spec.md")):
            sources.append(
                {
                    "path": spec_path.relative_to(change_dir).as_posix(),
                    "kind": "spec-delta",
                    "sha256": sha256_text(spec_path),
                }
            )
    return sources


def build_manifest(change_name: str, change_dir: Path, generated_at: str | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "changeName": change_name,
        "generatedAt": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": detect_sources(change_dir),
    }


def write_manifest(change_dir: Path, manifest: dict[str, Any]) -> Path:
    output_path = change_dir / "source-manifest.json"
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return output_path


def validator_errors(schema_path: Path, document: Any) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(document), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def freshness_report(manifest: dict[str, Any], change_dir: Path) -> tuple[list[str], list[str]]:
    stale: list[str] = []
    missing: list[str] = []
    for src in manifest.get("sources", []):
        rel = src.get("path")
        if not isinstance(rel, str) or not rel:
            continue
        path = change_dir / rel
        if not path.exists():
            missing.append(rel)
            continue
        if sha256_text(path) != src.get("sha256"):
            stale.append(rel)
    return stale, missing
