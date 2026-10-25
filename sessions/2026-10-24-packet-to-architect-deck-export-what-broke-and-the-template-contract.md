to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail.

# Deck export: what broke, and the template contract

## Step 1: what the existing exporter does

**What exists.**
- The exporter is `src/publishing/pptx_generator.py` (`PptxGenerator`).
- It is called only by the Dagster asset `rendered_course_file` (`src/publishing/assets.py`), which `/render/trigger` starts through Dagster's GraphQL.
- The asset reads the Project's TargetNodes (title, `content_markdown`, `target_layout`, `order`).
- It loads `cib-sources/templates/<name>.yaml` and the `.pptx` that file names, and saves the deck to MinIO `published/`.
- **No tests assert anything.**
  - `tests/test_direct_pptx_gen.py` prints its result and writes files into the working directory.
  - `tests/test_direct_pptx.py` is an inspection script over `test_docs/`.

**How it was run.**
- tr's hydraulics golden for step e has not landed, so the input was a consolidated course over the vendored fixture deck (`tests/fixtures/training/hydraulics_fixture.pptx`):
  - two sections, four leaves;
  - one leaf with a synthesizer image placeholder and one with an editor image link.
- The probe calls `PptxGenerator` exactly as the asset does, under three conditions:
  - A: no template config, which is what any install without `cib-sources/templates/` has;
  - B: the repo's own `config/master_engineering.yaml`, whose `.pptx` is not in the repo;
  - C: one node added by hand.

**What broke.**

1. **Traceback.** A node made by `/draft/node/add` has no `order`, and the exporter sorts on it: `TypeError: '<' not supported between instances of 'NoneType' and 'int'` (C). One hand-added node fails the whole export.
2. **Silent fallbacks at every step.**
   - A missing template config logs "Using defaults" and renders onto python-pptx's blank default deck.
   - An unmapped layout archetype becomes `documentary`, then whatever mapping comes first.
   - A layout index that is out of range becomes layout 0.
   - A placeholder index the layout lacks drops that content.

   In B, all 7 slides land on "Title Slide" and **every body is empty**. Nothing failed.
3. **Empty slides.**
   - Section nodes, the ones with children, get a content slide with an empty body (A: slides 2 and 4).
   - The title slide's subtitle placeholder is left empty (A: slide 1).
4. **Lost images.** The reservoir figure is missing in A and in B, and nothing reports it.
   - Images are fetched by URL with `requests`. The editor inserts either `/source/fixture-asset/…`, which is relative and cannot be fetched, or a presigned URL, which expires.
   - A layout with no image role drops the image without trying.
5. **Unresolved placeholders.** The synthesizer writes `{{asset_id}}` where an image goes, and nothing resolves it. A: slide 6 shows the literal text `{{slide_3_img_0}}`.
6. **Ordering ignores the tree.** The whole subtree is flattened and sorted on `order`. That is right only while every node carries the skeleton generator's global index. A hand-added node has none (finding 1).
7. **Unassigned content is exported** (from the code, not the probe). The asset never reads `is_unassigned` or `is_placeholder`, so an "Unassigned / For Review" section and its nodes would become slides.
8. **Not reachable on the deploy.**
   - `/render/trigger` calls Dagster at `DAGSTER_HOST` (default `localhost:3000`), and nothing in `training` runs Dagster. The route fails before the exporter starts.
   - That is from the configuration: no Dagster variable is set in the api pod. The route was not called.

**What the data offers but the exporter does not do.**
- **No source citations.** The source contract gives every slide its deck `filename` and its `number`, and wb holds `DERIVED_FROM` from each node to its slides. The exporter reads neither.
- **No concepts.** TargetNodes carry `key_concepts` from the skeleton, and source slides carry their `TEACHES` concepts. The exporter reads neither.
- **No speaker notes.**
- **Images.** The contract's image keys (`images/slide_{n}_img_{k}.png`) are not used; images are fetched by URL instead.

**In the repo already.**
- `config/master_engineering.yaml` names a template file ("Training Template.pptx") and maps its placeholder indices.
- `master_engineering` is the asset's default and appears in two scripts.
- If that is the customer template's name, the constraint says it should not be here. I could not find the text of ADR-0042 C3/C4: the ADR-0042 in invincible-agent covers live views and has no C clauses.
- I have taken the name out of every default (see below) but **not deleted the file**. Deleting it would not remove the name from history either. Your call.

## Steps 2–5: what I built

**Step 2: the contract** ([`docs/contracts/deck-template.md`](../docs/contracts/deck-template.md), 433f28b).
- The exporter reads a `.pptx` plus `deck-template.yaml`. Per role, the yaml names a layout and the placeholder `idx` for `title`, `body`, `citation` and `image`. `notes` takes `notes-page` or an `idx`, and defaults to the notes page.
- There are six roles: title, section, concept, concept-with-figure, summary, sources.
- **Unmapped role → `role 'concept-with-figure' is not mapped`.** The exporter checks the mapping, the course and every image before writing a slide. It raises all problems together and writes no file. Nothing falls back: no default role, no default layout, no "first layout".
- Content with nowhere to go also fails, so text is never dropped. This covers a leaf with an empty body, a leaf with no sources or no concepts, a second image on one leaf, and an image that will not resolve.
- No code names a template. A new template is one `.pptx` plus one yaml.

**Step 3: the stand-in** (`tests/fixtures/templates/standin/`, 036706c).
- `make_standin.py` generates `standin.pptx`: six layouts named for the roles, the default theme with no styling set, no slides. It is committed with its `deck-template.yaml`.
- It is the default everywhere: the Dagster asset, `RenderRequest`, `/render/templates` and the UI's template picker.

**Step 4: the golden** (`tests/test_deck_export_golden.py`).
- The hydraulics fixture course (`tests/fixtures/export/hydraulics-course.json`, over the vendored fixture deck) exports to 8 slides: title, section, concept, concept, section, concept-with-figure, summary, sources.
- The test asserts:
  - the layout names in order and every placeholder's text;
  - the picture on slide 6 only;
  - `Source: hydraulics_fixture.pptx, slide 3` / `Sources: hydraulics_fixture.pptx, slides 1, 2` on every concept slide;
  - the `Concepts:` line in each slide's notes;
  - the summary and sources slides.
- I re-exported the course and dumped it slide by slide myself; it matches.
- Not done: rendering the slides to images (the optional bonus).

**Step 5: round trip** (`check_round_trip`, `tests/test_deck_round_trip.py`).
- The check reads the written deck back and asserts:
  - the slide count and layout sequence;
  - every course concept exactly once;
  - every concept slide's citation equal to its sources;
  - a picture exactly where the role has one;
  - nothing in the summary, sources or citations that the course lacks.
- **It runs inside every export, not only in tests.** A failed check deletes the partial file.
- The tests take a good export and break it in seven ways: a citation deleted, a concept added to notes, a concept repeated, the picture removed, a picture added to a concept slide, an extra slide, two slides swapped. Each test asserts the check names the problem. The summary and sources comparisons have no corruption test of their own.

**Rewire** (e0992dc).
- `rendered_course_file` builds the course from the graph and exports through the new exporter:
  - the tree;
  - `DERIVED_FROM` to source slides, for the deck filename and slide number;
  - `key_concepts`, or else `TEACHES` by salience.
- Images resolve by MinIO key. The resolver accepts contract image keys, fixture references, presigned URLs (key only) and `{{asset_id}}`.
- `PptxGenerator` and its print-only test are deleted.

**Tests.** 207 → 250 passed, with 44 added and 1 removed:
- course builder: 17;
- mapping validation: 14;
- round trip: 8;
- golden: 3;
- stand-in: 2.

Frontend `tsc` is clean.

**Choices you may want to overrule.**
- The title role must map `body`: the subtitle "Consolidated from N source decks" always exists, and content is never dropped.
- Concept names compare exactly. "Pascal's law" and "Pascal's Law" count as two concepts.
- A mapping that sends two fields to one placeholder fails.
- A concept named by two leaves fails, naming both. In a consolidated course that means consolidation is not finished.

**Not verified.**
- The asset path (graph query → MinIO → export) has no test. It cannot run on the deploy until something in `training` runs Dagster (step-1 finding 8). The exporter it calls is fully tested.
- `config/master_engineering.yaml` is still in the repo, unreferenced, awaiting your call (above).
- ADR-0042 C3/C4: I followed the brief's wording (no customer template, names or styling vocabulary) without the ADR text.

**Commits.** 0833d01 (step 1), 433f28b (contract), 036706c (stand-in, exporter, golden, round trip), e0992dc (rewire). All pushed to `lane/wb`.
