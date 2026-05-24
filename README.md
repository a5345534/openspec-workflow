# openspec-workflow

Harness-neutral workflow core for OpenSpec-style change authoring.

This repo is designed around one rule:

> **workflow policy lives in scripts + schemas + project overlay, not inside any single agent harness.**

So instead of baking propose/archive behavior into Pi, Claude, Codex, or some other runtime, this project splits responsibilities like this:

- `skills/` — reusable skill instructions
- `prompts/` — generation prompt contracts
- `templates/` — deterministic fallback templates
- `schemas/` — machine-readable policy and artifact contracts
- `src/openspec_workflow/` + `scripts/` — executable workflow core
- `adapters/` — thin harness-specific wrappers

## Why this repo exists

Many teams want the same governed workflow shape:

- scaffold a change package
- keep markdown/spec files as SSOT
- generate a high-comprehension HTML explainer
- validate freshness, structure, locale, and layout
- block archive when required artifacts or tasks are not ready

But those rules should be reusable across projects and across agent harnesses.

`openspec-workflow` tries to provide exactly that reusable layer.

## Current capabilities

- scaffold a change directory
- generate `source-manifest.json`
- generate `change-explainer.html`
  - `template` backend: deterministic fallback, works offline
  - `opendesign` backend: optional daemon-backed generator
- validate explainer contract
- validate source-manifest freshness
- run archive preflight checks
- expose one real Pi adapter implementation while keeping the core harness-neutral

## Repository layout

```text
openspec-workflow/
├── adapters/
│   ├── claude/
│   ├── codex/
│   └── pi/
├── examples/
│   └── demo-project/
├── prompts/
├── schemas/
├── scripts/
├── skills/
├── src/openspec_workflow/
└── templates/
```

## Architecture

### 1. Core workflow engine

The Python package under `src/openspec_workflow/` is the executable source of truth.

It owns:

- change scaffolding
- manifest generation
- HTML generation orchestration
- validation
- archive readiness logic
- project policy loading

### 2. Project policy overlay

Each target project brings its own overlay file:

```text
<project-root>/.openspec-workflow.yaml
```

That file controls things like:

- where changes live
- where specs live
- whether explainers are required
- required semantic section ids
- locale/layout validation rules
- archive blocking rules
- default explainer backend

See:

- `examples/demo-project/.openspec-workflow.yaml`
- `schemas/project-policy.schema.json`

### 3. Thin harness adapters

Adapters should only:

- load shared skills/prompts
- expose wrapper commands or tools
- call the workflow scripts

Adapters should **not** reimplement:

- explainer contract
- archive rules
- source-manifest rules
- policy parsing
- validation logic

## Installation

### Python workflow core

```bash
cd /home/shawn/projects/active/openspec-workflow
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

### Pi package

This repo also includes a Pi package manifest (`package.json`) and a working Pi adapter.

Install into Pi directly from the repo path:

```bash
pi install /home/shawn/projects/active/openspec-workflow
```

Or from GitHub:

```bash
pi install git:github.com/a5345534/openspec-workflow
```

The Pi package loads the adapter extension, and the adapter loads this repo's shared `skills/` and `prompts/`.

## Command line usage

All shell wrappers call the same Python CLI.

### Scaffold a change

```bash
scripts/openspec-propose my-change --project-root /path/to/project
```

### Rebuild source manifest

```bash
scripts/openspec-build-source-manifest my-change --project-root /path/to/project
```

### Generate explainer

```bash
scripts/openspec-generate-explainer my-change --project-root /path/to/project --backend template
```

### Validate explainer

```bash
scripts/openspec-validate-explainer my-change --project-root /path/to/project
```

### Validate source manifest

```bash
scripts/openspec-validate-source-manifest my-change --project-root /path/to/project
```

### Archive preflight

```bash
scripts/openspec-archive-preflight my-change --project-root /path/to/project
```

## Pi adapter

A real first adapter implementation is included at:

- `adapters/pi/extension.ts`

It provides:

- shared skill/prompt discovery
- slash commands:
  - `/openspec-propose`
  - `/openspec-build-source-manifest`
  - `/openspec-generate-explainer`
  - `/openspec-validate-explainer`
  - `/openspec-validate-source-manifest`
  - `/openspec-archive-preflight`
- a tool:
  - `openspec_workflow`

The adapter only wraps the repo-local scripts. It does not fork workflow logic.

See `adapters/pi/README.md`.

## Open Design backend

The optional `opendesign` backend expects an HTTP daemon compatible with the Beyourself wrapper flow.

Policy keys:

- `changeExplainer.openDesign.daemonUrl`
- `changeExplainer.openDesign.projectPrefix`
- `changeExplainer.openDesign.agentId`
- `changeExplainer.openDesign.skillId`

Environment overrides:

- `OPENSPEC_OPEN_DESIGN_DAEMON_URL`
- `OPENSPEC_OPEN_DESIGN_AGENT_ID`
- `OPENSPEC_OPEN_DESIGN_SKILL_ID`
- `OPENSPEC_WORKFLOW_SKIP_BROWSER_LAYOUT_CHECK=1`

## Example project integration

A demo overlay lives at:

- `examples/demo-project/.openspec-workflow.yaml`

A real trial integration has also been applied to:

- `/home/shawn/projects/active/erpnext-source`

That trial adds:

- `.openspec-workflow.yaml`
- `docs/operations/openspec-workflow.md`
- an example change package under `openspec/changes/`

## Development notes

### Validate Python sources

```bash
python3 -m py_compile $(find src -name '*.py')
```

### Validate Pi adapter syntax

```bash
npx -y esbuild adapters/pi/extension.ts \
  --bundle \
  --platform=node \
  --format=esm \
  --external:@earendil-works/pi-ai \
  --external:@earendil-works/pi-coding-agent \
  --external:@earendil-works/pi-tui \
  --external:typebox \
  --outfile=/tmp/openspec-workflow-pi-extension.mjs
```

## Design rules

- markdown/spec files remain SSOT
- `change-explainer.html` is a companion view only
- the workflow core must remain runnable from plain shell / CI
- harness adapters must stay thin
- project-specific invariants belong in the project overlay, not the shared core

## License

MIT
