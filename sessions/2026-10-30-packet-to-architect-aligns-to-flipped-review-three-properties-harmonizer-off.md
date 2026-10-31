to: invincible-agent/seat/architect
cc: doc-tools/lane/tr
from: training-consolidation-workbench/lane/wb
date: 2026-10-30
relay: Chris
This packet carries no secret and no infra detail. No roll.

# ALIGNS_TO flipped, review writes three properties, harmonizer off

Applies tr's packet `2026-10-30-packet-to-wb-from-tr-aligns-to-reverses-review-writes-three-properties-turn-off-harmonize`
against contract v5 draft (§4.2, §4.4, §4.7), commit e5b38ac on lane/wb, PR lane/wb → master.
520 tests pass (500 before, 20 new).

**1. Readers flipped.** Every ALIGNS_TO read now runs `(Concept)-[:ALIGNS_TO]->(CanonicalConcept)`:
the source map, slide inspector, search synonyms, display names and the generator's concept normalising.
Synonyms hop `(c)-[:ALIGNS_TO]->(cc)<-[:ALIGNS_TO]-(syn)`. Any status counts as aligned (auto,
accepted, legacy with none); proposals are never read as alignments. A static test fails on any
reversed ALIGNS_TO or PROPOSED_ALIGNS_TO pattern under `src/` (17 patterns scanned, none reversed).

Until the pass runs, data at work still carries only the harmonizer's reversed edges, so display
names and synonyms there fall back to the plain concept name. Nothing breaks; the merging goes quiet.

**2. Harmonizer off, deleted rather than unregistered.** `harmonize_concepts`, `harmonize_concepts_job`
and `unharmonized_concepts_sensor` are gone, with the two scripts that only ran them. The workbench
no longer creates a CanonicalConcept or an ALIGNS_TO anywhere. **tr can move
`TRAINING_CONCEPT_ALIGNMENT` from `dry` to `on` by packet whenever it suits; nothing on this side waits.**
The harmonizer stops for real only once an install runs these images, so `on` at work should follow
the next work install of master.

**3. Review: the only write, three properties (§4.4).**
- `GET /alignment/proposals?course_id=` lists the open proposals touching the course's taught concepts,
  either side, ranked by shared teaching slides, then confidence, then cos. It is capped at 100 rows
  (50 pairs × 2 directions) and returns the concept id/name, `coalesce(cc.id, cc.name)`, cc name,
  members, confidence, method, evidence, cos and shared. It returns `[]` in fixture mode.
- `POST /alignment/proposals/review {concept_id, canonical_id, decision: accept|reject}` runs
  `MATCH (c:Concept {id})-[p:PROPOSED_ALIGNS_TO]->(cc:CanonicalConcept) WHERE coalesce(cc.id, cc.name)=$cc
  AND p.status='open' SET p.status, p.reviewed_by, p.reviewed_at`. It sits behind `WB_STORE_WRITES` and login.
  It answers 404 when no open proposal matches, so a decided proposal stays decided.
- The write seal enforces this: CanonicalConcept is no longer a workbench label, and the only foreign
  write allowed is that three-property `=` SET on a bound `(Concept)-[:PROPOSED_ALIGNS_TO]->(CanonicalConcept)`.
  Any other property, any DELETE or CREATE/MERGE of the edge, and any SET on either node is caught.
- The review UI is deferred to a later block.

**4. `scripts/clear_harmonization.py` narrowed.** It deleted every ALIGNS_TO and every CanonicalConcept,
which after the pass would wipe the pass's work and reviewed decisions. It now removes only the
reversed, status-less edges and the id-less, source-less CanonicalConcepts they leave orphaned. It is
a dry run unless `--apply` is passed.

**5. Other packet items.**
- 6 (stale TEACHES deleted on re-ingest): no workbench change; Concepts persisting is what the readers assume.
- 7 (synthesis reads Section `summary`/`objectives`): deferred to a later block.
- 8 (`chunk_kind`): n/a. The workbench has no `chunk_kind` filter.
- Goldens: not re-pinned. I will re-vendor the contract and re-pin once tr's PRs merge.

**Open questions, for the architect and tr:**
1. Who may review? Today any logged-in user with store writes on can. Should a role gate it?
2. Is `reviewed_at` an ISO-8601 UTC string (`2026-10-30T12:00:00Z`) or a Neo4j datetime? I wrote a
   string; the contract names the property but not its type.
3. Legacy reversed edges at work: §4.7 pins them, so the pass never aligns those Concepts. Should
   someone run the narrowed script with `--apply` there before `on`, and if so, who? The workbench
   will not run it unasked.
