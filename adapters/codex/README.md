# Codex adapter sketch

Codex integration should also be thin.

## Recommended shape

- expose shell wrappers or custom commands that call the shared scripts
- point Codex at the shared `skills/` directory when its runtime supports external skills
- keep all project-specific policy in `.openspec-workflow.yaml`

## Rule

Codex should orchestrate the workflow, not become the workflow implementation.
