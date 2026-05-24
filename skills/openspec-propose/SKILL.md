---
name: openspec-propose
description: Scaffold a new OpenSpec-style change, create proposal/design/tasks, generate source-manifest.json, and create change-explainer.html through the configured backend. Use when a repo wants a governed change package before implementation starts.
---

# openspec-propose

## Purpose

Create a new change package in a target project without depending on any specific agent harness.

## Expected inputs

- target project root
- change name (kebab-case)
- optional backend override (`template` or `opendesign`)

## Steps

1. Confirm the target project root.
2. Confirm or derive the change name.
3. Ensure the project has a policy overlay at `.openspec-workflow.yaml` or pass an explicit policy file.
4. Run:

```bash
scripts/openspec-propose <change-name> --project-root <project-root>
```

Optional backend override:

```bash
scripts/openspec-propose <change-name> --project-root <project-root> --backend template
```

## Output contract

A successful run should create:

- `.openspec.yaml`
- `proposal.md`
- `design.md`
- `tasks.md`
- `source-manifest.json`
- `change-explainer.html`

under:

```text
<project-root>/openspec/changes/<change-name>/
```

## Guardrails

- Treat markdown/spec files as the source of truth.
- Treat the HTML explainer as a companion view only.
- Prefer the configured backend; use `template` as the deterministic fallback.
- If the generated explainer fails validation, stop and fix the source files or backend output instead of hand-waving the failure.
