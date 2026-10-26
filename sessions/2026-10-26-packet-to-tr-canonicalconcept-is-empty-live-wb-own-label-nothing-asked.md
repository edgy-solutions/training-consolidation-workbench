to: doc-tools/lane/tr
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-26
relay: Chris
This packet carries no secret and no infra detail.

# CanonicalConcept is empty in the live graph: wb's own label, nothing asked of you

For your information only. No change to doc-tools or the contract.

**What the live graph shows.** It has no `CanonicalConcept` node and no `ALIGNS_TO` edge. Neo4j says so on each wb query that reads them: "label does not exist" (`01N50`) and "relationship type does not exist" (`01N51`). Since Generate Outline started working live today, these warnings show up whenever a draft loads. If you see them in the shared Neo4j logs, they come from wb, not from a gap on your side.

**Why it is empty.** Contract §4.4 makes `CanonicalConcept` and `ALIGNS_TO` wb's own. Their only writer is wb's concept-harmonization pipeline, which runs under Dagster, and Dagster is not deployed in the training install. wb's reads already fall back to the plain `Concept` name when no canonical concept exists, so the outlines are correct, just not merged across synonyms.

**When it fills.** Once wb's harmonization runs in-cluster, `(CanonicalConcept)-[:ALIGNS_TO]->(Concept)` edges will end on your `Concept` nodes. Rule 4 already covers them: a re-ingest MERGEs and never deletes a Concept, so the edges survive. There's nothing for you to do now.

**Still open from 10-24.** §4.4 still gives `ALIGNS_TO` as Concept → CanonicalConcept. The line should read CanonicalConcept → Concept, at your next revision.
