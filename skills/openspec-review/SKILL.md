---
name: openspec-review
description: Review an existing OpenSpec-style change package with attention to source-of-truth boundaries, explainer fidelity, source-manifest freshness, and archive readiness. Use during review or handoff.
---

# openspec-review

## Review focus

When reviewing a change package, inspect these artifacts together:

- `proposal.md`
- `design.md`
- `tasks.md`
- `specs/**/spec.md`
- `source-manifest.json`
- `change-explainer.html`

## Review questions

1. Does the explainer stay inside the facts stated by markdown/spec source files?
2. Does `source-manifest.json` still match the current source files?
3. Do the required explainer section ids exist?
4. Is the HTML self-contained and responsive?
5. Are unchecked tasks intentionally unresolved, or are they archive blockers?

## Useful commands

```bash
scripts/openspec-build-source-manifest <change-name> --project-root <project-root>
scripts/openspec-validate-explainer <change-name> --project-root <project-root>
scripts/openspec-archive-preflight <change-name> --project-root <project-root>
```

## Guardrails

- If HTML and markdown/spec disagree, markdown/spec wins.
- Prefer fixing source files and regenerating the explainer over manual HTML drift.
- Treat the workflow scripts as executable policy; do not re-interpret the contract ad hoc if the scripts already define it.
