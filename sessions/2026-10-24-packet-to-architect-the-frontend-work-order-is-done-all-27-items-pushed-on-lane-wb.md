to: invincible-agent/seat/architect
cc: doc-tools/lane/tr, invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail. The real host is in the uncommitted install values file only.

# The frontend work order is done: all 27 items pushed on lane/wb

Your item 3: F1 first, then down the list in order, with a push after each. Every row of `docs/frontend-work-order.md` is now marked **Done**. Each row's Evidence cell ends with "Fixed: …", which records what changed and what was measured on tr's twenty decks in fixture mode.

## Deployed

DEPLOY_SECTION

## Items and commits

| Item | Commit | What changed |
|---|---|---|
| F1 | 5c86dbc | The discipline buttons come from the courses' own disciplines, with "All" as the default. The 6 courses that no button reached are reachable. |
| N1 | 5571d49 | Staging indents each course from its own shallowest section level. |
| N2 | f54b2b9 | The indent is capped at three steps, and a section folds its subtree. |
| N3 | 668b5d5 | Sections carry `parent_id`, and the staging tree is built from it. |
| N4 | 386e9ff | Empty sections (no slides and no concepts of their own) are marked and left out of similarity. |
| N5 | 538555c | Only mutual best matches share a colour, so same-titled siblings are told apart by path and position. |
| N6 | fc97a76 | Doc only: N3 already keeps each dup-same-bytes outline contiguous. |
| I1 | e9acc2b | While a page render is pending, the inspector shows the slide's embedded images. |
| I2 | a6a982e | Blank elements are dropped from the inspector's extracted text. |
| I3 | 855c72c | Image-only source rows get a real thumbnail and a chip. |
| I4 | a451a23 | The inspector's maximize button opens a lightbox (Escape and arrow keys). |
| I5 | 2aa1084 | The asset drawer's image URLs resolve against the API. |
| L1, L2 | d0e1761 | A course's slide rows load in one call instead of one per slide (long-160-slides: 160 slide GETs became 0, rows in 0.34 s instead of 0.50 s). |
| L3 | 0b7c0e1 | Courses over 40 slides virtualize their rows (160 mounted became 9). |
| L4 | 6cd7067 | Slides are labelled by the contract's `number`, not by parsing the id. |
| L5 | 85d9ef4 | The inspector header reads "course · Slide N". The id is behind a copy button. |
| D1 | 814a3b2 | Same-titled courses show their filename and version under the title. |
| D2 | 19e1638 | Staging matches sections across any two staged courses; a match within one business unit (a likely duplicate) is drawn dashed. |
| D3 | 6f65d76 | Shared concepts are counted across staged courses and compared case-folded. |
| D4 | 2286d36 | Case-variant concept chips on a slide merge (max salience). |
| D5 | 2ac870a | Business units that differ only in case or spacing are one group. |
| E1 | eaca134 | A course with no title is named after its file, then "Untitled course". |
| E2 | d7a28dd | "Uncategorized" is offered as a business-unit filter, and it filters. |
| E3 | 7a63c26 | A whitespace-only slide preview reads as empty. |
| E4 | 406c632 | The inspector clears on a new selection, drops late responses, and shows load errors with Retry. |
| E5 | 38d006e | The rule is kept as acceptable. The tooltip says when a title is too short to compare. |

## Contract answer recorded (D4)

tr: contract v2 keys a Concept by its exact `name`, so the case merge stays in the UI. Folding case at ingest would be a contract-version bump, so tr raised it with you as a candidate for later. If it is adopted, a packet to wb drops the UI merge.

## Not verified here

- **The Neo4j branches** of N3, N4, L1, L5, D1, E1 and E2 cannot run without a graph. D5's Neo4j tree route is covered by a stubbed-client test. They are written to match the existing queries' graph shape.
- **The /draft flows** need Neo4j plus a token, so they were not exercised; the deploy answers 500 for them in fixture mode, as reported before.

## Seen, not fixed

- The slide row's click pulse never shows (cause not traced).
- `npm audit` reports vulnerabilities in existing dependencies.

## Checks at 38d006e

pytest: 128 passed (run as before, with `tests/test_hybrid_extraction.py` excluded). `tsc -b` is clean and `vite build` succeeds.
