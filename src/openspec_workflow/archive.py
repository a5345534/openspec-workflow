from __future__ import annotations

from pathlib import Path
from typing import Any

from openspec_workflow.policy import ProjectPolicy, resolve_change_dir
from openspec_workflow.validation import find_blocking_tasks, validate_explainer_artifact


class ArchivePreflightError(RuntimeError):
    pass


def archive_preflight(project_root: Path, policy: ProjectPolicy, change_name: str) -> dict[str, Any]:
    change_dir = resolve_change_dir(project_root, policy, change_name)
    if not change_dir.exists():
        raise ArchivePreflightError(f"Change directory not found: {change_dir}")

    report: dict[str, Any] = {
        "changeName": change_name,
        "changeDir": str(change_dir),
        "checks": {},
        "errors": [],
    }

    tasks_path = change_dir / "tasks.md"
    task_result = find_blocking_tasks(tasks_path, policy.archive.backlog_markers)
    report["checks"]["tasks"] = {
        "blocking": task_result.blocking,
        "backlog": task_result.backlog,
    }
    if policy.archive.require_no_unchecked_tasks and task_result.blocking:
        report["errors"].append("blocking_unchecked_tasks")

    if policy.archive.require_explainer:
        explainer_result = validate_explainer_artifact(change_name, change_dir, policy)
        report["checks"]["explainer"] = {
            "status": explainer_result.status,
            **explainer_result.data,
        }
        if explainer_result.status != "ok":
            report["errors"].append("invalid_change_explainer")

    report["status"] = "ok" if not report["errors"] else "fail"
    return report
