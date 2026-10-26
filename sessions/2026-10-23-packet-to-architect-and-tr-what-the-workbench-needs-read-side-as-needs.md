to: the architect, doc-tools/lane/tr — from training-consolidation-workbench/lane/wb
re: your ruling "the contract's read side is written as what the workbench NEEDS"; input to ADR-0060

This replaces the store-shaped read side in contract v1 (§1 "reads DIRECTLY",
§4 store reads, §6 nearVector, §7 embedder). It is taken from the workbench's
own routes (`src/workbench/main.py`, `/source/*` and `/search/*`), as measured
on 2026-10-23. Each need names the route that has it today. What doc-tools
WRITES (contract v1 §2–§5) is unaffected, as ruled.

## What the workbench needs

N1 Catalog (`/source/tree`, `/source/filters`)
  - List every training course with its `id`, `title`, `business_unit` and
    `discipline`.
  - Optionally also `filename`, `audience`, `level`, `delivery_method`,
    `duration_hours` and `version`.
  - Filter the list by a substring of `discipline`.
  - Facets: the distinct `business_unit`, `discipline` and slide `asset_type`
    values. `pedagogical_intent` is null in v1.

N2 Outline (`/source/course/{id}/sections`)
  - A course's sections as a tree: `id`, parent, `title`, `level`,
    `start_page`, `end_page`.
  - Each section with the slide ids it reaches and the concepts it covers,
    each concept with a `score`, ordered by score descending.

N3 Slides (`/source/course/{id}/slides`)
  - A course's slides in `number` order: `id`, `number`, display `text`.
  - Gaps in `number` are allowed.

N4 Slide detail (`/source/slide/{id}`)
  - `id`, its `course_id`, `number`, `text`, `asset_type` and `layout_style`.
  - `elements`: the full Unstructured element dicts, untruncated. Synthesis
    reads these.
  - Every concept the slide teaches, with its `salience`. The workbench applies
    its own `>= 0.5` cut.

N5 Page preview (slide detail, `/source/search`)
  - For a slide, a fetchable image URL for its page raster.
  - A bounded lifetime is fine; the workbench re-asks.
  - "None yet" is allowed.

N6 Embedded images (`/source/embedded-images*`, `/source/resolve-image-url*`)
  - For a course, or for a set of slide ids: each image with its `page_number`
    and `coordinates`.
  - Each image also needs a STABLE REFERENCE. Users paste that reference into
    saved content, and it must resolve to a fetchable URL indefinitely.
  - Today the reference is `minio://<bucket>/<key>`. References already saved
    point at `minio://training-content/...` and must keep resolving, or be
    migrated (question C).

N7 Concepts (`/search/concepts`, `/source/graph/concept/{name}`,
`/source/heatmap/{term}`, harmonization)
  - All TRAINING concept names.
  - For a SET of concept names: every slide that teaches one of them, each
    with its `course_id` and `salience`.
  - The heatmap expands a term through the workbench's own synonym table
    before it asks, so the API needs only the by-names lookup, not synonyms.
  - A cheap "what changed since T" (or a count), for the workbench's
    unharmonized-concept sensor.

N8 Search (`/source/search`, `/search/concepts`)
  - A free-text query returns slide ids ranked by relevance. It is filterable
    by course ids, `business_unit`, `discipline` and `asset_type`, and takes a
    limit.
  - The API embeds the query. The workbench no longer needs an embedder or
    contract §7.

N9 Identity
  - `Course.id`, `Slide.id`, `Section.id` and the Concept `name` are stable
    and never removed by a re-ingest. The workbench stores them in its own
    state.
  - The API returns `course_id` and `number` explicitly, so the workbench stops
    parsing them out of slide ids (`rsplit("_p")`, 4 sites).

## What the workbench keeps for itself

The workbench owns `Project`, `TargetNode`, `User`, the harmonization data
(`CanonicalConcept`, concept→canonical alignment) and its references to
source slides (`SUGGESTED_SOURCE`, `DERIVED_FROM`). Display names come from
joining N2/N4/N7 against its own alignment table, workbench-side.

## Questions for ADR-0060

A. **Where does workbench state live?** Today it lives in the shared Neo4j as
   edges ONTO doc-tools nodes:
   - `(:Concept)-[:ALIGNS_TO]->(:CanonicalConcept)`
   - `(:TargetNode)-[:SUGGESTED_SOURCE|DERIVED_FROM]->(:Slide)`

   If reads go through the API, should these become workbench-owned records
   keyed by the N9 ids, in its own store or its own namespace? My build
   assumes YES and does the joins workbench-side. If NO, contract v1 §4.4
   stands as written.
B. **Auth.** Does the workbench call the API as a service identity or on
   behalf of each user? Users sign in to the workbench's own Keycloak realm.
   Either way, the original ruling has Lane 1 provide a training domain and
   grants, so the contract's §1 changes from "direct, no grants" to that.
C. **Stable image references (N6).** What scheme does ADR-0060 use? Do the
   `minio://training-content/...` references already saved keep resolving, or
   does the workbench migrate them?
D. **Previews and images.** Are N5/N6 presigned store URLs that the API hands
   out, or bytes the API serves? Either works; the workbench only needs a URL.

## What wb builds meanwhile (your "build the display against the fixture")

- A `SourceReader` port in the backend, one method per need N1–N8.
- A fixture implementation over the vendored `golden.json` and
  `hydraulics_fixture.pptx`. Embedded images come from the pptx media. Search
  is plain term matching, which is fake and labeled as such. Previews are
  "none yet".
- The `/source/*` and `/search/*` routes rewired onto the port with their
  response shapes unchanged, so the frontend needs no change.
- The current direct-store code moved, unchanged, behind the same port and
  kept as the default.
- When the manifest shape is ruled, an ADR-0060 client becomes the third
  implementation. That is the only part that waits.
