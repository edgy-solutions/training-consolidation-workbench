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
