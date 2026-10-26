to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-26
relay: Chris
This packet carries no secret and no infra detail.

# 03335a8 rolled: revision 19, template readback

- **What rolled:** lane/wb 03335a8 as revision 19, under the lock. The gate is green (`/healthz`
  and `/` answer 200) and the lock is released. The pods run api `sha256:75008de0…` and ui
  `sha256:e79bf431…`, the digests in the work-install packet. So the digests Chris installs are
  the ones that ran.
- **The "stand-in, no URI" line:** it appears once in the api log,
  `deck template: DECK_TEMPLATE_URI is not set; exports use the stand-in template`.
- **`/render/templates`:** `{"templates":["standin"]}`.
- **One export:** done in the api pod through the live template path (`configured_mapping()` →
  the stand-in mapping), on the hydraulics fixture course. It gave 8 slides on the stand-in
  layouts (title, section ×2, concept ×2, concept-with-figure, summary, sources), 33.5 KB, with 0
  round-trip problems.

**Why it used a fixture course: no sandbox draft can export yet.** I tried all ten drafts that
have sections, and every one failed export validation before reaching the template:
- 30 sections have an empty body and no source slides. They were never synthesized.
- 8 drafts are one-node shells with no source decks.
- 57 problems report one concept on two sections.

The last kind matters past the sandbox. In 4c17070a, whose labels carry no weight suffix,
"Pascal's Law" sits on both "Hydraulic Systems Fundamentals" and "Knowledge
Assessment". An assessment section reuses its course's concepts by nature, so a synthesized
outline with an assessment section will still be refused. I have not changed the rule; it is
yours to call. My suggestion: allow a concept on more than one section, or exempt assessment
sections.
