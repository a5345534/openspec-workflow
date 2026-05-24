# Claude adapter sketch

Claude-side integration should be wrapper-only.

## Recommended shape

- load the shared skills from this repo
- create slash-command or command-markdown wrappers that shell out to:
  - `scripts/openspec-propose`
  - `scripts/openspec-build-source-manifest`
  - `scripts/openspec-generate-explainer`
  - `scripts/openspec-validate-explainer`
  - `scripts/openspec-archive-preflight`
- keep project-specific invariants in `.openspec-workflow.yaml`

## Rule

Do not fork the workflow rules into command prompts if the scripts already encode them.
