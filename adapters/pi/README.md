# Pi adapter sketch

Pi should stay a thin adapter.

## Recommended shape

- load `skills/` from this repo
- expose repo-local script commands as Pi commands
- optionally add a tiny extension that points Pi to the shared skills/prompts
- do **not** reimplement validation or scaffolding logic inside the extension

## Minimal integration ideas

- `resources_discover` → add this repo's `skills/` and `prompts/`
- command `/openspec-propose` → call `scripts/openspec-propose`
- command `/openspec-archive` → call `scripts/openspec-archive-preflight`

## Why

The reusable contract should live in the workflow scripts and policy overlay, not in Pi-specific code.
