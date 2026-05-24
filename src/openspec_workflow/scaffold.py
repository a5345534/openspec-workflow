from __future__ import annotations

import datetime as dt
from pathlib import Path

from openspec_workflow.manifest import build_manifest, write_manifest
from openspec_workflow.policy import ProjectPolicy, resolve_change_dir

PROPOSAL_TEMPLATE = """## Why

Describe the problem, pressure, or opportunity that makes this change necessary.

## What Changes

- Describe the main behavior or workflow changes.
- Describe the main artifacts or modules affected.
- Describe any important constraints or non-goals.

## Capabilities

### New Capabilities
- List new capability names here.

### Modified Capabilities
- List modified capability names here.

## Impact

- List directly affected technical surfaces.
- List related but unchanged surfaces.

## Scope

### In
- In-scope item

### Out
- Out-of-scope item
"""

DESIGN_TEMPLATE = """## Context

Summarize the current state and the design pressure behind the change.

## Goals

- Goal 1
- Goal 2

## Decisions

### D1. Name the first decision

**Choice**
- Describe the chosen direction.

**Rationale**
- Explain why this direction is preferred.

**Alternative rejected**
- Explain what was considered and why it was not chosen.

## Risks / Trade-offs

- Risk 1
- Risk 2

## Migration Plan

1. Step 1
2. Step 2
3. Step 3

## Open Questions

- Question 1
"""

TASKS_TEMPLATE = """## 1. Planning
- [ ] Confirm scope and affected capabilities
- [ ] Confirm project policy overlay assumptions

## 2. Implementation
- [ ] Implement the required behavior
- [ ] Update documentation or templates as needed

## 3. Validation
- [ ] Run relevant validation commands
- [ ] Confirm explainer generation / update

## 4. Follow-up backlog
- [ ] [BACKLOG] Optional polish or future follow-up
"""

SPEC_YAML_TEMPLATE = """name: {change_name}
created: {created}
status: draft
"""


class ScaffoldError(RuntimeError):
    pass


def scaffold_change(
    project_root: Path,
    policy: ProjectPolicy,
    change_name: str,
    *,
    force: bool = False,
    with_manifest: bool = True,
) -> Path:
    change_dir = resolve_change_dir(project_root, policy, change_name)
    if change_dir.exists() and any(change_dir.iterdir()) and not force:
        raise ScaffoldError(f"Change already exists and is not empty: {change_dir}")

    change_dir.mkdir(parents=True, exist_ok=True)
    created = dt.datetime.now(dt.timezone.utc).date().isoformat()
    (change_dir / ".openspec.yaml").write_text(
        SPEC_YAML_TEMPLATE.format(change_name=change_name, created=created)
    )
    (change_dir / "proposal.md").write_text(PROPOSAL_TEMPLATE)
    (change_dir / "design.md").write_text(DESIGN_TEMPLATE)
    (change_dir / "tasks.md").write_text(TASKS_TEMPLATE)

    specs_dir = change_dir / "specs"
    specs_dir.mkdir(exist_ok=True)
    (specs_dir / ".gitkeep").write_text("")

    if with_manifest:
        manifest = build_manifest(change_name, change_dir)
        write_manifest(change_dir, manifest)

    return change_dir
