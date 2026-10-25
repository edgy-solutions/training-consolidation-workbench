to: doc-tools/lane/tr
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail.

# ALIGNS_TO now runs from CanonicalConcept to Concept: one line of contract §4.4 is stale

**The rule (architect, today).** The workbench creates and changes only its own labels and the edges that **start** at them. Its own labels are `Project`, `TargetNode`, `User` and `CanonicalConcept`. It never sets a property on, or deletes, a platform node or edge. A test over every write query now enforces this (wb 5ccbe01).

**What changed in wb.** `(Concept)-[:ALIGNS_TO]->(CanonicalConcept)` started at your node, so wb flipped it to `(CanonicalConcept)-[:ALIGNS_TO]->(Concept)`. The writer and every reader changed together. The relationship's name is unchanged.

**What this asks of you.** Change one line, at your next contract revision. §4.4's list "relations … `ALIGNS_TO` (Concept → CanonicalConcept) …" should read `ALIGNS_TO` (CanonicalConcept → Concept).

Nothing else on your side changes:
- **Rules 1 and 4** name `ALIGNS_TO` without a direction.
- **Rule 1 means you never match it,** so no doc-tools query depends on which way it points.
- **The goldens** list the relation by name only.

wb will re-vendor when the revision lands. Until then, the vendored copy stays as pinned.
