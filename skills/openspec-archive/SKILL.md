---
name: openspec-archive
description: Run archive-readiness checks for an OpenSpec-style change package. Use before promoting a change into the authoritative spec tree or declaring implementation complete.
---

# openspec-archive

## Purpose

Check whether a change is ready to archive according to the target project's policy overlay.

## Steps

1. Confirm the target project root and change name.
2. Run:

```bash
scripts/openspec-archive-preflight <change-name> --project-root <project-root>
```

3. Review the output for:
   - blocking unchecked tasks
   - missing or invalid `change-explainer.html`
   - stale or invalid `source-manifest.json`
   - presentation contract failures

## Guardrails

- An unchecked task is blocking unless it is explicitly backlog-marked.
- The explainer is never a replacement for markdown/spec artifacts.
- Fix the source files or policy problems; do not bypass validation unless the project policy explicitly allows it.
