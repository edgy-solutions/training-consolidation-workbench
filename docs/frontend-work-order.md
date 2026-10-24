# Frontend work order: what the year-old UI gets wrong about real decks

Lane wb, for Monday. It covers the source side of the workbench: the tree,
the slide rows, the inspector, and the staging columns. Each item gives the
file and line, what goes wrong, and the fix.

**Evidence** column:
- `code`: found by reading the frontend against the contract v2 shapes the
  fixture reader serves.
- `deck: <slug>`: seen in fixture mode on that one of tr's case decks
  (`tests/fixtures/training/<slug>/`).

Items marked `code` are waiting for the deck that proves or disproves them.

**Size**: S is under an hour, M is half a day, L is a day or more.

**Done** in the `#` column: fixed on lane/wb, worked in order from F1 (architect, 2026-10-24).
The Evidence cell then ends with what the fix measured.

## Case 0: reaching the decks at all

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| F1 **Done** | `frontend/src/components/TopBar.tsx:16-21`, `frontend/src/store.ts:49` | The discipline buttons are hardcoded (ME, EE, SWE, SysE), the store defaults to Mechanical, there is no "All", and the choice persists in `workbench-storage`. The tree request always carries `engineering_discipline`, so only Mechanical courses show on load. Any course whose discipline is not one of the four, or that has none, can't be reached at all. | Build the buttons from `/source/filters` `domains`, add "All" as the default, and drop a persisted value that no longer exists. | S | deck: 8 of 20 courses render on load. 6 (Hydraulics, Materials, Instrumentation, Safety, Avionics, and empty-no-metadata) can't be reached from any button. Fixed: "All" is the default and all 20 render on load; Hydraulics alone shows 1; a persisted Mechanical from before (store version 0) and a stale value both reset to All; the nine buttons fit at 1280 px. |

## Case 1: nested sections

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| N1 **Done** | `frontend/src/components/StagingArea.tsx:577`, `:597` | The backend sends top-level sections as `level: 1`, but the UI treats 0 as top (`api.ts:38` says so too). So every section is indented one step, and the top-level arrow style (`indentLevel === 0`) never shows. | Normalize to `level - minLevel` per course, and fix the `api.ts` comment to match the contract. | S | deck: all 13 decks with sections send levels from 1, none from 0. Fixed: on "Electrical Safety Programme" (levels 1 and 2), level-1 rows went from 16px with the sub-section arrow to 0px with the top-level arrow, and level-2 rows from 32px to 16px. |
| N2 **Done** | `StagingArea.tsx:597` | Indent is `16px * level` with no cap and no collapse. A 4-level outline loses about 64px of a narrow column, and long titles wrap into slivers. | Cap the visual indent at 3 steps, show depth with a number or guide line past that, and let a parent collapse its subtree. | M | deck: nested-sibling-same-title arrives 5 levels deep (1 to 5). Fixed: on its course (14 sections) the deepest rows sit at 48px instead of 64px and carry a level badge (4 rows past the cap). Collapsing the top-level parent leaves 1 of 14 rows; expanding restores all 14. A folded section's rows drop out of hover and highlight; matching still runs over every section. |
| N3 **Done** | `StagingArea.tsx:575` | Sections render as a flat list in whatever order the API returns. The tree shape relies entirely on that order being depth-first, and nothing checks it. | Build the tree from section ids (`<course>_s1_s0` encodes the parent) or have the API return `parent_id`, then render recursively. | M | code. Fixed: `/source/course/{id}/sections` returns `parent_id` (the fixture reader passes the deck's, the Neo4j query reads `HAS_SECTION`); all 16 fixture courses carry it, none dangling. StagingArea walks the tree depth-first from `parent_id` and falls back to level order without it. dup-same-bytes (15 sections, 3 roots) renders each root followed by its own subtree, live depths 0 1 2 2 2 1 2 2, then 0 1 1 1, then 0 1 1. `tests/test_section_parent_id.py` pins the ids. |
| N4 **Done** | `StagingArea.tsx:572` | An empty section (no slides, no concepts) looks exactly like a populated one. The only empty state is the whole course showing "No sections found". | Show a muted "empty" badge, and leave empty sections out of similarity scoring. | S | deck: dup-same-bytes (10 of 15 sections concept-less), long-with-blank-gaps (3 of 150). nested-empty-section itself arrives with no empty section (ingest). Fixed: sections now carry `slide_count` and `concepts_inherited` (true when the course-concept fallback filled them in), so emptiness is visible to the UI. A section with no slides and only inherited concepts gets a muted "empty" badge and is left out of similarity candidates, colour groups and shared concepts; hovering it finds nothing to highlight. dup-same-bytes: 10 badges of 15 sections, matching its 10 slide-less, concept-less sections; the other 5 have slides. The 150-section course found in the fixture (Systems Familiarisation Course; not confirmed to be long-with-blank-gaps) has 3 concept-less sections, all with slides, so none is badged. `tests/test_section_empty.py` pins both fields. |
| N5 **Done** | `StagingArea.tsx:114-130` | Sibling sections with the same title in one course both match the same section in another column. The colour map then assigns one colour to three sections, and click-to-scroll jumps to the first one. | Break ties on path (parent titles) and position, not title alone. | M | deck: long-160-slides and long-with-hidden-slides ("ARINC 429 Basics", "Lockout and Tagout"), long-with-blank-gaps. nested-sibling-same-title arrives without its same-titled siblings (ingest). Fixed: candidates rank by score, then parent-path similarity, then nearer relative position, then id; colours join only mutual best matches between two columns. Measured with Core (160) and Refresher (146) in two columns (the fixture puts all long decks in one BU, so the probe moved Refresher to its own): colour groups went from 13 (largest 27, all holding same-titled siblings of one course) to 69 mutual pairs (largest 2, none with siblings); coloured rows 306 to 138. Clicking Refresher "Lockout and Tagout" (row 14) now scrolls Core to row 14, not row 2; 50 of 146 clicks change target. Seen on the way, not fixed: the click's pulse never shows (the hover re-render resets the class). |
| N6 **Done** | `src/workbench/source_routes.py:80` | dup-same-bytes is one Course carrying two outlines (contract: a re-ingest of the same bytes adds a second one). The route sorts every section by `start_page`, so the two outlines interleave into one list: 15 sections over 3 slides, 8 distinct titles. | Nothing on the frontend until step g closes it. If it ships before then, group sections by their top-level ancestor id so each outline at least stays contiguous. | S | deck: dup-same-bytes-a/b. Fixed by N3: StagingArea walks each top-level section's subtree depth-first, so each outline's sections stay together under their root; on dup-same-bytes the 15 sections render as 3 roots, each followed by its own subtree (depths 0 1 2 2 2 1 2 2, then 0 1 1 1, then 0 1 1). The duplicated outline itself remains until step g. |

## Case 2: image-only slides

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| I1 **Done** | `frontend/src/components/SlideInspector.tsx:307-315` | The image pane shows only `s3_url`, the page render. Until step e ships there are no `pages/` keys, so every slide says "No Image Available". On an image-only slide the inspector then has no image, no text and no concepts: it looks broken. | When `s3_url` is empty, show the slide's embedded images (already served via `/source/course/{id}/images` and the fixture-asset route). Label the pane "page render pending" rather than as an error. | M | deck: all 20 decks, 0 slides with `s3_url`; every slide inspected shows "No Image Available". Fixed: with no `s3_url` the pane loads the slide's embedded images (`/source/embedded-images-for-slides`), labelled "Page render pending · embedded image i of N" with a thumbnail strip when N > 1; with none it shows a muted "Page render pending / No embedded images on this slide" instead of an error. 9 of 575 fixture slides carry embedded images, and all 9 are image-only (Connector Identification Guide p2 with 4, Wiring Diagram Pack p1-p4 among them): they now show their images where they showed nothing. Backend-relative asset paths are prefixed with `API_URL` (they failed to load when UI and API ran on different origins); AssetDrawer uses the same paths unprefixed. |
| I2 **Done** | `SlideInspector.tsx:368-383` | `Image` elements (and any element whose `text` is empty) render as a type label above an empty bordered block. | Render `Image` elements as a thumbnail or placeholder, and skip elements whose text is empty after trimming. | S | deck: no golden has an `Image` element. Image slides arrive with no text (image-only-deck 4 of 4, image-only-slide p2, image-full-bleed p2), so only the empty-text half applies. Fixed: elements whose text is blank after trimming are dropped (Image elements stay, as a muted icon with the filename or alt text), and a slide left with none falls back to its text preview or "No text content extracted.". 558 of 575 fixture slides carry a blank element, every one a `PageBreak`; 0 Image elements. Connector p2 and Wiring p1 went from a PAGEBREAK label over an empty block to the fallback line; a text slide went from 3 blocks (1 empty) to 2. |
| I3 **Done** | `frontend/src/components/SourceBrowser.tsx:465-469` | The row thumbnail is also `s3_url` only, so before step e every row shows the same grey icon and image-only slides can't be told apart. | Fall back to the first embedded image, and show an "image-only" chip when the slide has no text elements. | S | deck: image-only-deck, image-only-slide, image-full-bleed. Fixed: expanding a course makes one `/source/embedded-images-for-slides` call and maps each image to its slide by `page_number`; a row without `s3_url` shows its slide's first embedded image, and an "image-only" chip when the slide has an image and no text. Connector Identification Guide: 1 of 3 rows with a real thumbnail and chip (p2, its only image slide); Wiring Diagram Pack: 4 of 4; a text-only course: 0 thumbnails, 0 chips; 1 call per expansion each. |
| I4 **Done** | `SlideInspector.tsx:316-318` | The maximize button has no handler. | Wire it to a lightbox or remove it. | S | code. Fixed: the button opens a full-screen lightbox of the pane's image (page render, else the selected embedded image); Escape, the backdrop and a close button shut it, and the arrow keys or buttons step through embedded images with the pane following. Hidden when there is no image. Connector p2: lightbox image 640px wide, two ArrowRight presses reach image 3, Escape leaves the pane on "image 3 of 4"; a no-image slide shows no button. |
| I5 **Done** | `frontend/src/components/AssetDrawer.tsx:41` | Multiple images per slide and full-bleed images are reachable only from the synth-block asset drawer, not while browsing sources. | Covered by I1. Verify the drawer once the `image-multi-per-slide` and `image-full-bleed` goldens land. | S | code. Fixed: both goldens are in the fixture (image-multi-per-slide is Connector Identification Guide, image-full-bleed is Hangar Safety Tour, images on p2 and p3). The drawer now renders image URLs through `assetSrc` (backend-relative fixture paths did not load cross-origin); the inserted markdown keeps the backend URL. Verified by mounting the drawer directly on Connector p2: 1 request, 4 images listed, each 640px wide. The synth-block wiring is not verified: `/draft` needs Neo4j and a login, so fixture mode cannot create a draft. |

## Case 3: long decks

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| L1 **Done** | `SourceBrowser.tsx:346` | Expanding a course fires one `GET /source/slide/{id}` per slide, all at once through `Promise.all`. A 160-slide deck makes 160 parallel requests. | Return the row fields (`s3_url`, top concepts) from `/source/course/{id}/slides` in one call, as the search endpoint already does. Fetch details only for the inspector. | M (with a backend change) | deck: long-160-slides fires 160 requests on expand (0.65 s local, 1.0 s through the training-namespace ingress, fixture mode); long-with-hidden-slides 150 (1.6 s local). Each one is a Neo4j query in direct mode. Fixed: `/source/course/{id}/slides` returns the row fields (`s3_url`, `text_preview`, concepts, elements, plus the old `number` and `text`) in one call, built by the same code as `/source/slide/{id}` in fixture mode and by one Cypher query plus one MinIO listing in Neo4j mode (untested here). Expanding long-160-slides: 160 slide GETs to 0, 0.50 s to 0.34 s to 160 rows; Wiring Diagram Pack rows unchanged. `test_route_slides` checks every slide against the details route. |
| L2 **Done** | `SourceBrowser.tsx:347-350` | If one of those requests fails, the whole course shows "No slides found." | Falls out of L1. Until then, use `Promise.allSettled` and show the failed rows. | S | code. Fixed with L1: one request, and a failed one shows "Couldn't load slides." with Retry; "No slides found." only for an empty list. With the call aborted the message shows; after unblocking, Retry loads the rows. |
| L3 **Done** | `SourceBrowser.tsx:388-392` | No virtualization: 160 draggable rows, each with up to 6 concept chips, all mounted. Several long courses expanded at once compound this. | Virtualize the slide list (`@tanstack/react-virtual`); dnd-kit works with it. | M | deck: long-160-slides mounts 160 rows. Fixed: a course over 40 slides virtualizes its rows (`@tanstack/react-virtual` 3.13.26) against the panel's shared scroller, with measured row heights; shorter courses and search results keep plain rows. long-160-slides expanded mounts 9 rows (11 at the bottom, slide 160 visible); with long-with-hidden-slides also open, 18 to 31 rows depending on scroll, both lists reaching their last slide. Dragging slide 26 shows the overlay, which survives its row unmounting. |
| L4 **Done** | `SourceBrowser.tsx:481`, `frontend/src/components/SynthBlock.tsx:64` | The slide label is parsed from the id (`id.split('_p')[1]`) rather than taken from `number`. `SynthBlock` has no fallback, so it shows "Slide undefined" for any other id shape. Hidden or skipped slides make the label depend on the id scheme, not on the contract field. | Use `number` from the API. Add it to the `SourceSlide` type (`api.ts:12`). | S | deck: refuted for this set. Ids and `number` agree on all 20 decks and no "Slide undefined" shows, since hidden slides are ingested and numbered like any other. Keep as hygiene. Fixed: `SourceSlide` carries `number`, and one helper `slideLabel` (`api.ts`) labels a slide by `number`, else by the id's `_pN` suffix, else by the whole id. The source tree passes `number`; `SynthBlock` has only the id and now falls back instead of showing "Slide undefined". Wiring Diagram Pack still reads Slide 1 to 4. |
| L5 **Done** | `SlideInspector.tsx:302` | The inspector header shows the raw slide id: `sha256:` plus 64 hex plus `_pN`, about 75 characters of mono text. It has no course title and no slide number. | Show "Course title, slide N" and put the id behind a copy button. | S | code. Fixed: `/source/slide/{id}` also sends `number`, `course_id` and `course_title` (optional fields; the course slide list sends them too), and the header reads "Wiring Diagram Pack · Slide 2", with the full id in its tooltip and behind a copy button. `test_slide_course_label` checks the fields against the tree and the slide list for 6 courses. The Neo4j query is unrun. |

## Case 4: duplicate names

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| D1 **Done** | `SourceBrowser.tsx:381`, `StagingArea.tsx:250` | Two courses with the same title in the same BU look identical in the tree and in the staging column. Nothing distinguishes them: no filename, date, slide count or id. | Show a secondary line with the source filename or slide count, and a short id on hover. | S | deck: dup-title-a/b render as two identical "Pump Maintenance Basics" rows under Industrial Pumps. Fixed: the tree sends each course's contract `filename` and `version` (both readers), and the tree row and the staging column header show them under the title ("dup-title-a.pptx · v1.0", "dup-title-b.pptx · v2.0"), with the title and a 12-hex short id in the tooltip. Clicking the title or the subtitle still expands the course. The Neo4j queries are unrun. |
| D2 **Done** | `StagingArea.tsx:114-130`, `:176` | Similarity matching runs only across BU columns (`g1 >= g2` skips the same column). Two same-BU duplicates are never compared, which is exactly when a reviewer needs them compared. | Allow same-column matches between different courses, styled differently from cross-BU matches. | M | code. Fixed: candidates and mutual best matches are per course, not per column, so two courses in one business unit are compared; a section whose partners are all in its own column is drawn with a dashed border in its group colour (`data-match="same-bu"`), and cross-BU matches look as before. All 33 fixture courses in one column: 0 coloured sections became 271, all same-bu. The same courses split into 3 BUs: 271 coloured before and after, all cross-bu. The dup-title pair cannot show it, since dup-title-b has no sections. |
| D3 | `StagingArea.tsx:290-314` | Shared concepts are computed only when there are 2 or more BUs, and by exact string. With one BU, nothing is shared. "Pressure" and "pressure" count as two concepts here, though the similarity code lowercases them (`:43`). | Compare case-folded everywhere, and display the most common casing. | S | deck: dup-concept-case (2 pairs); the long decks 90 to 100 pairs each |
| D4 | `SourceBrowser.tsx:490-502`, `SlideInspector.tsx:325-358` | Case-variant concepts on one slide render as two chips with separate saliences. | Merge chips by case-folded name and keep the max salience. Whether the backend should merge them instead is a contract question for tr. | S | deck: dup-concept-case; the long decks carry 90 to 100 case-variant pairs each (ingest casing varies by slide), so this is the common case, not an edge case |
| D5 | `SourceBrowser.tsx:208` | React key `bu.name`: harmless while the backend groups by name, but two BUs that differ only in case or whitespace become two groups. | Normalize the BU name in the backend `_course_tree` (`src/workbench/source_routes.py:32`). | S | code |

Identical bytes in two folders (`dup-same-bytes-{a,b}`) are one Course by
contract §3. The fixture reader already merges them, keeping the first
folder (commit 4e3656c). Expect one tree entry.

## Case 5: empty text

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| E1 | `src/workbench/source_routes.py:37`, `SourceBrowser.tsx:381` | A course with no title is sent as `name: null`. The tree row is then an invisible, still-clickable blank strip, and the staging column header is empty. | The backend falls back to the deck filename, then to "Untitled course". The frontend also renders a muted placeholder when `name` is empty. | S | deck: refuted for this set. empty-title takes its title from the sidecar and empty-no-metadata gets the filename stem; no course arrives nameless. The placeholder stays as a guard. |
| E2 | `source_routes.py:32` | No metadata means no BU, so the course is filed under "Uncategorized". That is fine, but the filter dropdown (`facets`) has no "Uncategorized" option, so the course can't be filtered back in. | Emit "Uncategorized" in the facets when any course lacks a BU. | S | deck: empty-no-metadata files under "Uncategorized"; `/source/filters` origins has no such entry |
| E3 | `SlideInspector.tsx:368-387` | Blank slide: no elements, so the inspector falls back to `text_preview` and then to "No text content extracted." That part is fine. But whitespace-only elements, or notes-only text, render as empty bordered blocks (see I2). | Trim before deciding a slide is empty. A separate speaker-notes block is not possible: the contract sends notes as ordinary slide text, ahead of the body. | S | deck: whitespace-only elements on all 20 decks (159 on long-160-slides); empty-whitespace-and-notes p3, p4 |
| E4 | `SlideInspector.tsx:41-46` | If the details fetch fails, it only logs to the console. `slide` keeps its previous value, so the inspector shows the last slide's details under the new selection, or "Loading details..." forever if there was none. This is the same class of bug as the outline header fixed in c956c9a. | Clear `slide` when the selection changes, and add an error state. | S | code |
| E5 | `StagingArea.tsx:32-34` | Title similarity drops words of 2 characters or fewer, and an empty title scores 0. Sections with empty or very short titles ("Q&A", "Lab") can match only on concepts. | Acceptable. Note it in the UI's match tooltip. | - | code |

## Fixed tonight, because it blocked looking at the decks

- **Null salience.** tr's case goldens are pre-step-d, so every TEACHES edge
  has `salience: null`. Three things broke on that:
  - Both concept-chip renderers guarded with `!== undefined` and then called
    `null.toFixed()`. Expanding a course or opening a slide would crash the
    whole app.
  - The search route did `max(prev, None)`, which raised as soon as a slide
    taught a concept twice.

  The chip guards now use `!= null`, `ConceptNode.salience` is typed
  `number | null`, `source_routes._max_salience` treats None as unknown, and
  `tests/test_fixture_null_salience.py` covers it.
- **Grey chips are expected.** A chip with no salience number against these
  goldens is the step-d ingest gap, not a frontend bug, and is not listed
  below. Every slide row's chips will sort in arbitrary order until step d
  lands and the goldens are regenerated, which changes their sha256s.

## Seen on the decks, but not frontend work

These are what the sandbox ingest wrote into tr's goldens. The UI shows them faithfully. Most are
already in the contract's gaps list; the first two are not, and go to tr.

- **nested-four-levels arrives with 0 sections.** The outline step returned none for it, so the
  4-level case never reaches the UI. nested-sibling-same-title came back 5 levels deep instead,
  and it carries the depth evidence for N2.
- **The designed edge cases are sampled away.** nested-empty-section has no empty section, and
  nested-sibling-same-title has no same-titled siblings. The outline is an LLM sample. The long
  decks and dup-same-bytes carry both cases instead (N4, N5).
- **Hidden slides carry no marker** (contract gaps list). The UI can't mark them hidden until a
  Slide property exists.
- **Speaker notes are slide text** (contract gaps list). See E3.

## Not covered here

- The old `.github/workflows/build-container.yml` targets `main` and a
  Dagster image. It has never run, and it was left as it was. Images come
  from `build-images.yml`.
- Synth-side views (`SlidePreview`, `MarkdownEditor`) render the generated
  target slides, not source decks, so this deck set doesn't exercise them.

## Deck evidence log

One row per case deck as it is opened in fixture mode: the commit it came
from, and the items it confirms, refutes or adds.

| Deck | Golden sha256 (8) | Confirms | Refutes | New |
|---|---|---|---|---|
| hydraulics (root) | 88017f94 | N1 (levels 1 and 2, no 0); I1 (0 of 4 slides have `s3_url`); I2/E3 (3 whitespace-only elements render as empty blocks) | L1 at this size: 4 requests, 0.14 s, harmless | The golden has no `Image` elements although slide 4 embeds a picture, so image-only slides will likely arrive as text-less slides, not as `Image` elements. I2's "render Image elements" may then have nothing to render, which makes I1's embedded-image fallback the real fix. |
| 20 case decks (lane/tr-decks e50d0df, vendored in d4283ec) | per-deck pins in `VENDORED.json` | F1 (new), N1, N2, N4, N5, N6 (new), I1, I2 (empty-text half), I3, L1, L3, D1, D3, D4, E2, E3 | L4 (ids and numbers agree); E1 (no nameless course) | COVERS `score` is null pre-step-d too; the sections route answered 500 on every deck with sections until a5e83e5. |
