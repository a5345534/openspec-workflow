# Open Design Change Explainer Prompt

You are generating an OpenSpec `change-explainer.html` companion artifact.

## Authority and source rules

- `proposal.md`, `design.md`, `tasks.md`, and any spec delta files are the authoritative sources.
- `change-explainer.html` is a companion view, not a second SSOT.
- Do **not** introduce requirements, promises, migrations, or constraints that are absent from the source files.
- If the source files are ambiguous, stay conservative and summarize only what is clearly grounded.

## Workflow rules

- Read `source-manifest.json` first.
- Then read every source file listed in `source-manifest.json` before writing the final artifact.
- Do **not** ask discovery questions.
- Do **not** emit `question-form` blocks.
- Your only durable output is `change-explainer.html` in the current project root.

## Output contract

Write a single self-contained `change-explainer.html` file that:
- is directly readable offline
- does not depend on remote CSS, remote JavaScript, remote fonts, or CDN assets
- uses inline CSS / inline JS / inline SVG only when needed
- uses Traditional Chinese (繁體中文) for reader-facing prose, headings, labels, and navigation chrome by default, except for literal identifiers that must stay unchanged
- declares `<html lang="zh-Hant">`
- uses a responsive document-style reading layout that remains readable on mobile, tablet, and desktop widths without horizontal overflow or clipped panels
- does **not** use a fixed 1920×1080 stage, viewport-scaling slide shell, or hidden-overflow deck container as the primary reading experience
- contains these semantic section ids exactly:
  - `why`
  - `what-changes`
  - `before-after`
  - `flow`
  - `affected-surfaces`
  - `scope-boundaries`
  - `rollout`
  - `current-status`

## Quality bar

A reviewer should be able to open the HTML first and understand:
1. why the change exists
2. what changes
3. what is different before vs after
4. the end-to-end flow
5. affected modules / technical surfaces
6. in-scope vs out-of-scope boundaries
7. rollout / migration expectations when relevant
8. current status

If your output would violate the authority boundary, the Traditional Chinese locale contract, the responsive non-overflow layout contract, or the self-contained HTML constraint, stop and choose a simpler presentation instead of inventing unsupported structure.
