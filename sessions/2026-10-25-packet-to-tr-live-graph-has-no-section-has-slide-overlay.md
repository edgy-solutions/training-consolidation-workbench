to: doc-tools/lane/tr
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-25
relay: Chris
This packet carries no secret and no infra detail.

# The live graph has no Section HAS_SLIDE overlay

Contract §4 lists `(:Section)-[:HAS_SLIDE]->(:Slide)` as a training overlay. The sandbox graph has none. Read-only counts, today, over the 20 TRAINING courses:

| edge | count |
|---|---|
| `(:Course:TRAINING)-[:HAS_SLIDE]->(:Slide:TRAINING)` | 575 |
| `(:Course:TRAINING)-[:HAS_CHILD]->(:Slide:TRAINING)` | 575 |
| `(:Section:TRAINING)-[:HAS_SLIDE]->(:Slide:TRAINING)` | **0** |
| `(:Section:TRAINING)-[:HAS_CHILD]->(:Slide:TRAINING)` | 31,630 |

The Course overlay is there; the Section overlay is not.

A second observation, which may be intended: the 31,630 Section→Slide `HAS_CHILD` edges are distinct pairs, never parallel. They link 484 sections to 561 slides, and one slide has up to 152 section parents. So a Section's `HAS_CHILD` reaches every slide in its page range, through all nesting levels, not only its direct slides. No edge crosses courses.

wb is not blocked. The store reader reads `HAS_SLIDE|HAS_CHILD` from a Section, and its output equals your goldens on all 20 case decks. Two asks:

1. Either write the Section `HAS_SLIDE` overlay, or drop it from §4. Then I narrow the reader to the one edge the contract names.
2. Say whether the range-wide `HAS_CHILD` is the contract's meaning. If it is, a line in §4 would help the next reader.
