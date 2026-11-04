to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-11-03
relay: Chris
This packet carries no secret and no infra detail.

# Deck defects (3) and (4) are in PR #14, stacked on #13

**Needed from you:** review #14 and make the two calls below. Nothing is rolled from it.

## What it does

- **(3) Headings:** a `#` or `##` body line becomes a bold level-0 paragraph with no bullet, never a bold bullet. A leading heading that repeats the slide title is removed.
- **(4) Sections:** a section slide shows the parent's synthesized summary. A section with no body gets no slide and is listed under `skipped_sections` in the render record, on `render_overrides`, with `reason`, `by` and `at` null when nothing was overridden.

`deck_template` stays 1. Whole suite: 734 passed. The real draft, run locally with its real parent summaries, gives 16 slides, no round-trip problems, no title-only section and no bold bullet. Not opened in PowerPoint.

## Two calls

1. **Differing `#` lines: I kept them.** You allowed "strip or demote". All 8 leaves on the real draft open with a `#` line that differs from the slide title, for example `Brushless vs Static Excitation` over `# Choose the Right Excitation System`. Stripping them drops reviewed text and breaks "content is never dropped", so I demoted them. The cost: every content slide reads title, bold line, bold line, bullets. If you'd rather strip them, it's a one-line change plus the contract line. Chris's PowerPoint check is a good moment to judge it.
2. **A mapping with no section `body`: I skip the slide, as you ruled.** On such a mapping every section divider disappears, even when a summary exists. The mapping gets a warning and the render record lists them. Work's mapping needs checking before work takes this: if it maps only a title for `section`, it needs a body placeholder, or its dividers go.
