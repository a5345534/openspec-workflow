from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_REQUIRED_SECTIONS = [
    "why",
    "what-changes",
    "before-after",
    "flow",
    "affected-surfaces",
    "scope-boundaries",
    "rollout",
    "current-status",
]

DEFAULT_BACKLOG_MARKERS = [
    "backlog",
    "follow-up",
    "follow up",
    "後續",
    "待辦",
    "另案",
]


@dataclass(slots=True)
class OpenDesignPolicy:
    daemon_url: str = "http://127.0.0.1:7456"
    project_prefix: str = "openspec-workflow"
    agent_id: str | None = None
    skill_id: str | None = None


@dataclass(slots=True)
class ChangeExplainerPolicy:
    required: bool = True
    locale: str = "zh-Hant"
    required_sections: list[str] = field(default_factory=lambda: DEFAULT_REQUIRED_SECTIONS.copy())
    min_cjk_chars: int = 24
    backend: str = "template"
    require_viewport_meta: bool = True
    allow_remote_dependencies: bool = False
    skip_browser_layout_check_env: str = "OPENSPEC_WORKFLOW_SKIP_BROWSER_LAYOUT_CHECK"
    open_design: OpenDesignPolicy = field(default_factory=OpenDesignPolicy)


@dataclass(slots=True)
class ArchivePolicy:
    require_explainer: bool = True
    require_no_unchecked_tasks: bool = True
    legacy_policy_start: str | None = None
    backlog_markers: list[str] = field(default_factory=lambda: DEFAULT_BACKLOG_MARKERS.copy())


@dataclass(slots=True)
class ProjectPolicy:
    project_root: Path
    changes_dir: Path
    specs_dir: Path
    change_explainer: ChangeExplainerPolicy = field(default_factory=ChangeExplainerPolicy)
    archive: ArchivePolicy = field(default_factory=ArchivePolicy)


class PolicyError(RuntimeError):
    pass


def _read_policy_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PolicyError(f"Policy file not found: {path}")
    text = path.read_text()
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise PolicyError(f"Policy file must contain an object: {path}")
    return payload


def _resolve_dir(project_root: Path, raw: str | None, default: str) -> Path:
    rel = raw or default
    path = Path(rel)
    if path.is_absolute():
        return path
    return project_root / path


def default_policy(project_root: Path) -> ProjectPolicy:
    return ProjectPolicy(
        project_root=project_root,
        changes_dir=project_root / "openspec" / "changes",
        specs_dir=project_root / "openspec" / "specs",
    )


def load_policy(project_root: Path, policy_path: Path | None = None) -> ProjectPolicy:
    if policy_path is None:
        default_path = project_root / ".openspec-workflow.yaml"
        if not default_path.exists():
            return default_policy(project_root)
        policy_path = default_path

    payload = _read_policy_payload(policy_path)
    policy = default_policy(project_root)

    project_block = payload.get("project", {})
    if project_block and not isinstance(project_block, dict):
        raise PolicyError("project must be an object")
    policy.changes_dir = _resolve_dir(project_root, project_block.get("changesDir"), "openspec/changes")
    policy.specs_dir = _resolve_dir(project_root, project_block.get("specsDir"), "openspec/specs")

    explainer_block = payload.get("changeExplainer", {})
    if explainer_block and not isinstance(explainer_block, dict):
        raise PolicyError("changeExplainer must be an object")
    policy.change_explainer.required = bool(explainer_block.get("required", policy.change_explainer.required))
    policy.change_explainer.locale = str(explainer_block.get("locale", policy.change_explainer.locale))
    sections = explainer_block.get("requiredSections")
    if isinstance(sections, list) and sections:
        policy.change_explainer.required_sections = [str(item) for item in sections]
    policy.change_explainer.min_cjk_chars = int(
        explainer_block.get("minimumCjkChars", policy.change_explainer.min_cjk_chars)
    )
    policy.change_explainer.backend = str(explainer_block.get("backend", policy.change_explainer.backend))
    policy.change_explainer.require_viewport_meta = bool(
        explainer_block.get("requireViewportMeta", policy.change_explainer.require_viewport_meta)
    )
    policy.change_explainer.allow_remote_dependencies = bool(
        explainer_block.get("allowRemoteDependencies", policy.change_explainer.allow_remote_dependencies)
    )
    policy.change_explainer.skip_browser_layout_check_env = str(
        explainer_block.get(
            "skipBrowserLayoutCheckEnv",
            policy.change_explainer.skip_browser_layout_check_env,
        )
    )

    open_design_block = explainer_block.get("openDesign", {})
    if open_design_block and not isinstance(open_design_block, dict):
        raise PolicyError("changeExplainer.openDesign must be an object")
    policy.change_explainer.open_design.daemon_url = str(
        open_design_block.get("daemonUrl", policy.change_explainer.open_design.daemon_url)
    )
    policy.change_explainer.open_design.project_prefix = str(
        open_design_block.get("projectPrefix", policy.change_explainer.open_design.project_prefix)
    )
    agent_id = open_design_block.get("agentId", policy.change_explainer.open_design.agent_id)
    skill_id = open_design_block.get("skillId", policy.change_explainer.open_design.skill_id)
    policy.change_explainer.open_design.agent_id = str(agent_id) if agent_id else None
    policy.change_explainer.open_design.skill_id = str(skill_id) if skill_id else None

    archive_block = payload.get("archive", {})
    if archive_block and not isinstance(archive_block, dict):
        raise PolicyError("archive must be an object")
    policy.archive.require_explainer = bool(
        archive_block.get("requireExplainer", policy.archive.require_explainer)
    )
    policy.archive.require_no_unchecked_tasks = bool(
        archive_block.get("requireNoUncheckedTasks", policy.archive.require_no_unchecked_tasks)
    )
    legacy_policy_start = archive_block.get("legacyPolicyStart", policy.archive.legacy_policy_start)
    policy.archive.legacy_policy_start = str(legacy_policy_start) if legacy_policy_start else None
    backlog_markers = archive_block.get("backlogMarkers")
    if isinstance(backlog_markers, list) and backlog_markers:
        policy.archive.backlog_markers = [str(item).lower() for item in backlog_markers]

    return policy


def resolve_change_dir(project_root: Path, policy: ProjectPolicy, change_name: str) -> Path:
    return policy.changes_dir / change_name


def package_root() -> Path:
    return Path(__file__).resolve().parents[2]
