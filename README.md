# openspec-workflow

Harness-neutral workflow core for OpenSpec-style change authoring.

This project is intentionally split into layers:

- `skills/` — reusable skill instructions and policy overlays
- `prompts/` — explainer-generation prompt contracts
- `templates/` — deterministic fallback templates
- `schemas/` — machine-readable contracts
- `scripts/` + `src/openspec_workflow/` — reusable CLI workflow engine
- `adapters/` — thin harness-specific examples

## Goals

- keep workflow rules outside any single agent harness
- make scripts the executable source of truth
- let each project bring its own policy overlay
- let each harness implement only a thin adapter

## Included workflows

- scaffold a new change directory
- generate `source-manifest.json`
- generate `change-explainer.html`
  - `template` backend: deterministic fallback, works offline
  - `opendesign` backend: optional daemon-backed generator
- validate explainer contract
- run archive preflight checks

## Quick start

```bash
cd /home/shawn/projects/active/openspec-workflow
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

cp examples/demo-project/.openspec-workflow.yaml /path/to/your/project/.openspec-workflow.yaml

scripts/openspec-propose demo-change --project-root /path/to/your/project
scripts/openspec-build-source-manifest demo-change --project-root /path/to/your/project
scripts/openspec-generate-explainer demo-change --project-root /path/to/your/project --backend template
scripts/openspec-validate-explainer demo-change --project-root /path/to/your/project
scripts/openspec-archive-preflight demo-change --project-root /path/to/your/project
```

## Project policy overlay

By default the engine looks for a policy file at:

```text
<project-root>/.openspec-workflow.yaml
```

A project overlay controls things like:

- where change directories live
- whether explainers are required
- required semantic section ids
- locale and layout validation rules
- archive blocking rules
- default explainer backend

See:

- `examples/demo-project/.openspec-workflow.yaml`
- `schemas/project-policy.schema.json`

## Command summary

All repo-local wrappers call the same Python CLI.

- `scripts/openspec-propose`
- `scripts/openspec-build-source-manifest`
- `scripts/openspec-generate-explainer`
- `scripts/openspec-validate-explainer`
- `scripts/openspec-archive-preflight`

## Open Design backend

The optional `opendesign` backend expects an HTTP daemon compatible with the Beyourself wrapper flow.

Config keys:

- `openDesign.daemonUrl`
- `openDesign.projectPrefix`
- `openDesign.agentId`
- `openDesign.skillId`

Environment overrides:

- `OPENSPEC_OPEN_DESIGN_DAEMON_URL`
- `OPENSPEC_OPEN_DESIGN_AGENT_ID`
- `OPENSPEC_OPEN_DESIGN_SKILL_ID`
- `OPENSPEC_WORKFLOW_SKIP_BROWSER_LAYOUT_CHECK=1`

## Harness adapters

This repo treats harness adapters as thin shells.

- `adapters/pi/`
- `adapters/claude/`
- `adapters/codex/`

They should call the workflow scripts, not reimplement workflow rules.

## Status

This is a working scaffold for a reusable workflow-core repo, with deterministic fallback generation and reusable validation logic already implemented.
