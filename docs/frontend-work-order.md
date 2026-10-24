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

## Case 1: nested sections

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| N1 | `frontend/src/components/StagingArea.tsx:577`, `:597` | The backend sends top-level sections as `level: 1`, but the UI treats 0 as top (`api.ts:38` says so too). So every section is indented one step, and the top-level arrow style (`indentLevel === 0`) never shows. | Normalize to `level - minLevel` per course, and fix the `api.ts` comment to match the contract. | S | code; hydraulics returns levels 1 and 2 |
| N2 | `StagingArea.tsx:597` | Indent is `16px * level` with no cap and no collapse. A 4-level outline loses about 64px of a narrow column, and long titles wrap into slivers. | Cap the visual indent at 3 steps, show depth with a number or guide line past that, and let a parent collapse its subtree. | M | code |
| N3 | `StagingArea.tsx:575` | Sections render as a flat list in whatever order the API returns. The tree shape relies entirely on that order being depth-first, and nothing checks it. | Build the tree from section ids (`<course>_s1_s0` encodes the parent) or have the API return `parent_id`, then render recursively. | M | code |
| N4 | `StagingArea.tsx:572` | An empty section (no slides, no concepts) looks exactly like a populated one. The only empty state is the whole course showing "No sections found". | Show a muted "empty" badge, and leave empty sections out of similarity scoring. | S | code |
| N5 | `StagingArea.tsx:114-130` | Sibling sections with the same title in one course both match the same section in another column. The colour map then assigns one colour to three sections, and click-to-scroll jumps to the first one. | Break ties on path (parent titles) and position, not title alone. | M | code |

## Case 2: image-only slides

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| I1 | `frontend/src/components/SlideInspector.tsx:307-315` | The image pane shows only `s3_url`, the page render. Until step e ships there are no `pages/` keys, so every slide says "No Image Available". On an image-only slide the inspector then has no image, no text and no concepts: it looks broken. | When `s3_url` is empty, show the slide's embedded images (already served via `/source/course/{id}/images` and the fixture-asset route). Label the pane "page render pending" rather than as an error. | M | code; seen on hydraulics slide 4 |
| I2 | `SlideInspector.tsx:368-383` | `Image` elements (and any element whose `text` is empty) render as a type label above an empty bordered block. | Render `Image` elements as a thumbnail or placeholder, and skip elements whose text is empty after trimming. | S | code |
| I3 | `frontend/src/components/SourceBrowser.tsx:465-469` | The row thumbnail is also `s3_url` only, so before step e every row shows the same grey icon and image-only slides can't be told apart. | Fall back to the first embedded image, and show an "image-only" chip when the slide has no text elements. | S | code |
| I4 | `SlideInspector.tsx:316-318` | The maximize button has no handler. | Wire it to a lightbox or remove it. | S | code |
| I5 | `frontend/src/components/AssetDrawer.tsx:41` | Multiple images per slide and full-bleed images are reachable only from the synth-block asset drawer, not while browsing sources. | Covered by I1. Verify the drawer once the `image-multi-per-slide` and `image-full-bleed` goldens land. | S | code |

## Case 3: long decks

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| L1 | `SourceBrowser.tsx:346` | Expanding a course fires one `GET /source/slide/{id}` per slide, all at once through `Promise.all`. A 160-slide deck makes 160 parallel requests. | Return the row fields (`s3_url`, top concepts) from `/source/course/{id}/slides` in one call, as the search endpoint already does. Fetch details only for the inspector. | M (with a backend change) | code |
| L2 | `SourceBrowser.tsx:347-350` | If one of those requests fails, the whole course shows "No slides found." | Falls out of L1. Until then, use `Promise.allSettled` and show the failed rows. | S | code |
| L3 | `SourceBrowser.tsx:388-392` | No virtualization: 160 draggable rows, each with up to 6 concept chips, all mounted. Several long courses expanded at once compound this. | Virtualize the slide list (`@tanstack/react-virtual`); dnd-kit works with it. | M | code |
| L4 | `SourceBrowser.tsx:481`, `frontend/src/components/SynthBlock.tsx:64` | The slide label is parsed from the id (`id.split('_p')[1]`) rather than taken from `number`. `SynthBlock` has no fallback, so it shows "Slide undefined" for any other id shape. Hidden or skipped slides make the label depend on the id scheme, not on the contract field. | Use `number` from the API. Add it to the `SourceSlide` type (`api.ts:12`). | S | code |
| L5 | `SlideInspector.tsx:302` | The inspector header shows the raw slide id: `sha256:` plus 64 hex plus `_pN`, about 75 characters of mono text. It has no course title and no slide number. | Show "Course title, slide N" and put the id behind a copy button. | S | code |

## Case 4: duplicate names

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| D1 | `SourceBrowser.tsx:381`, `StagingArea.tsx:250` | Two courses with the same title in the same BU look identical in the tree and in the staging column. Nothing distinguishes them: no filename, date, slide count or id. | Show a secondary line with the source filename or slide count, and a short id on hover. | S | code |
| D2 | `StagingArea.tsx:114-130`, `:176` | Similarity matching runs only across BU columns (`g1 >= g2` skips the same column). Two same-BU duplicates are never compared, which is exactly when a reviewer needs them compared. | Allow same-column matches between different courses, styled differently from cross-BU matches. | M | code |
| D3 | `StagingArea.tsx:290-314` | Shared concepts are computed only when there are 2 or more BUs, and by exact string. With one BU, nothing is shared. "Pressure" and "pressure" count as two concepts here, though the similarity code lowercases them (`:43`). | Compare case-folded everywhere, and display the most common casing. | S | code |
| D4 | `SourceBrowser.tsx:490-502`, `SlideInspector.tsx:325-358` | Case-variant concepts on one slide render as two chips with separate saliences. | Merge chips by case-folded name and keep the max salience. Whether the backend should merge them instead is a contract question for tr. | S | code |
| D5 | `SourceBrowser.tsx:208` | React key `bu.name`: harmless while the backend groups by name, but two BUs that differ only in case or whitespace become two groups. | Normalize the BU name in the backend `_course_tree` (`src/workbench/source_routes.py:32`). | S | code |

Identical bytes in two folders (`dup-same-bytes-{a,b}`) are one Course by
contract §3. The fixture reader already merges them, keeping the first
folder (commit 4e3656c). Expect one tree entry.

## Case 5: empty text

| # | Where | What goes wrong | Fix | Size | Evidence |
|---|---|---|---|---|---|
| E1 | `src/workbench/source_routes.py:37`, `SourceBrowser.tsx:381` | A course with no title is sent as `name: null`. The tree row is then an invisible, still-clickable blank strip, and the staging column header is empty. | The backend falls back to the deck filename, then to "Untitled course". The frontend also renders a muted placeholder when `name` is empty. | S | code |
| E2 | `source_routes.py:32` | No metadata means no BU, so the course is filed under "Uncategorized". That is fine, but the filter dropdown (`facets`) has no "Uncategorized" option, so the course can't be filtered back in. | Emit "Uncategorized" in the facets when any course lacks a BU. | S | code |
| E3 | `SlideInspector.tsx:368-387` | Blank slide: no elements, so the inspector falls back to `text_preview` and then to "No text content extracted." That part is fine. But whitespace-only elements, or notes-only text, render as empty bordered blocks (see I2). | Trim before deciding a slide is empty. If notes are in the contract, show them in their own "Speaker notes" block. | S | code |
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
