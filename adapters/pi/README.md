# Pi adapter

This directory now contains a working thin Pi adapter.

## Files

- `extension.ts` — the adapter implementation

## What it does

The adapter intentionally keeps Pi-specific logic thin.

It does **not** reimplement the workflow core. Instead it:

- exposes the repo's shared `skills/` and `prompts/`
- registers wrapper slash commands
- registers one `openspec_workflow` tool for agent-side use
- shells out to the shared repo scripts under `scripts/`

## Commands

- `/openspec-propose`
- `/openspec-build-source-manifest`
- `/openspec-generate-explainer`
- `/openspec-validate-explainer`
- `/openspec-validate-source-manifest`
- `/openspec-archive-preflight`

## Tool

- `openspec_workflow`

Actions:

- `propose`
- `build-source-manifest`
- `generate-explainer`
- `validate-explainer`
- `validate-source-manifest`
- `archive-preflight`

## Install into Pi

From the local repo:

```bash
pi install /home/shawn/projects/active/openspec-workflow
```

From GitHub:

```bash
pi install git:github.com/a5345534/openspec-workflow
```

Then reload Pi if it is already running:

```text
/reload
```

## Design rule

If the workflow contract changes, update the shared scripts / schemas / policy behavior first.

Only update this adapter when Pi-specific ergonomics need to change.
