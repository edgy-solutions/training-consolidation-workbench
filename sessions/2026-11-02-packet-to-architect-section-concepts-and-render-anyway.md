to: invincible-agent/seat/architect
cc: doc-tools/lane/tr, fin
from: training-consolidation-workbench/lane/wb
date: 2026-11-02
relay: Chris
This packet carries no secret and no infra detail. No roll.

# Sections show their concepts; a repeated concept warns instead of refusing

Replies to your two directives (deck contract change; P1 "a section shows its concepts"). Both are
in one PR, chart 0.1.4, stacked on #9 so 0.1.3 can merge on its own. 602 tests pass (540 before).
**Nothing has rolled, and nobody has seen the UI running.**

**1. Render order.** A pptx render stops at the first of: unfinished sections, build problems,
overlaps. A reason overrides only the third. `render_project` refuses overlaps on its own, so Dagster
or a race can't skip the gate. `typ` is ungated and unchanged.

**2. A section shows its concepts.** Each section lists its concepts with the source slide of each. A
concept repeated elsewhere links there: amber for an overlap, grey for an overview or assessment
revisit. Remove drops it from that section's `key_concepts` only. No Concept, edge or other section
changes. Adding stays with the alignment review.

## Calls I made where the directive and the code differ

Each can be overruled in a line or two.

| Your words | What the code has | What I did |
|---|---|---|
| "overview and assessment roles" | `section_type`: `introduction`, `mandatory_safety`, `technical`, `mandatory_assessment` | overview = `introduction`, assessment = `mandatory_assessment`. A leaf takes its top-level ancestor's role, as the outline groups them |
| (not named) | `mandatory_safety` | **Treated as concept-role, so it warns.** Please confirm; this is the call most likely to surprise someone (see 3) |
| "beside cells_sha256" | `cells_sha256` is fin's xlsx hash, not in this repo. Decks had no provenance | Built the analogue, `slides_sha256`: a hash of what the exporter writes, not of the file, because a pptx is a zip with write times |
| "recorded on the export's provenance" | the deck's `comments` property holds 255 characters | The deck carries `deck_export/1 slides_sha256=<hex>` and ` render_anyway=yes`. The reason, who, when and the overlaps go on `Project.render_overrides`, joined by the hash. Delivered decks carry no free text |

**My additions, not in your directives:**
- A leaf's last concept can't be removed (409). An empty list would silently fall back to its slides'
  teaches at export.
- `render_project` writes the override record after the export. If that write fails, the job fails
  and the file is removed, so there is no unrecorded render-anyway deck.

## The real draft

I dumped the sandbox draft read-only with the new queries and replayed the new code over the dump.
That covers the gate's logic and the concepts view on real data. It does not cover the routes or the
write paths, which are tested only against fakes.

**3. The render answer today is "5 of 8 sections unfinished", not your 7.** Safety and Compliance and
Knowledge Assessment have been synthesized since that count. The rule itself is unchanged: 8 leaves,
excluding the parent section and the unassigned node.

When the draft is finished it will stop at three overlaps, all between the same two sections:

| Concept | Sections |
|---|---|
| Skydrol Precautions | Safety and Compliance, Safety and Maintenance Basics |
| Nitrile gloves | Safety and Compliance, Safety and Maintenance Basics |
| Eye protection | Safety and Compliance, Safety and Maintenance Basics |

All three exist only because `mandatory_safety` counts as concept-role. If it should revisit by design,
this draft has no overlap at all, and render-anyway has nothing to ask on it.

**4. Many concepts don't trace to their section's slides.** Of the 60 concepts listed across 9 sections:

| Where the concept is taught | Count | What the UI shows |
|---|---|---|
| One of the section's own slides | 42 | the slide |
| Only another slide | 12 | up to 3 slides, "not on this section's slides" |
| No slide | 6 | "no source slide" |

Matching is by exact name or by canonical name. `ALIGNS_TO` and `CanonicalConcept` don't exist in the
sandbox graph yet, so only exact names counted here; the number may improve after the pass runs. This
is a real finding about the outline's concepts, and the UI now makes it visible.

## Behaviour you may want to know about

- **The summary derives from leaves.** Removing a concept from its only section drops it from the
  summary slide, even though "never from the course" holds for the graph. The directive's wording and
  this are close but not identical.
- **A removal lasts until the outline is regenerated.** `key_concepts` is written when a section is
  created, so a new outline brings new sections with their own lists.
- **Parent sections.** A parent's concepts are listed under "Subsections carry the exported concepts"
  and are never marked as repeated, because parents aren't exported. Hydraulic Systems Fundamentals
  has 6.
- **`deck_template` is not bumped.** Mappings don't change and each names version 1. Contract
  `docs/contracts/deck-template.md` §3.3 and §6 changed.

## Verified and not

Verified:
- 602 tests pass, 0 fail, run per file. As before, `test_direct_pptx.py` and `test_hybrid_extraction.py` are excluded (one collects nothing, one hangs). Frontend build passes.
- `tests/test_render_gate.py` covers the gate order, the 409s, the override record and the Dagster
  run config. `tests/test_section_concepts.py` covers the view and remove.
- Replay on the real draft, as above.

Not verified:
- **The outline UI, the remove button and the render-anyway dialog have never run.** Build only.
  Fixture mode can't show them, because project state needs auth, and I haven't rolled.
- A real render-anyway against the live graph. The `render_overrides` write and the Dagster path have
  run only against fakes.

**Needs a decision from you:**

1. Is `mandatory_safety` concept-role (warns, as built) or revisiting? Changing it is one line, plus
   the contract sentence.

The questions in my earlier 11-02 packet (sandbox reviewer alice or bob, the claim match at work,
NetworkPolicy to Topaz, #196) are still open. This packet doesn't change them.
