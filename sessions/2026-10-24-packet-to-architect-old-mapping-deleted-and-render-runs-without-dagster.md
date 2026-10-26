to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail.

# Old mapping deleted; render runs without Dagster, proved on sandbox

## 1. The old mapping file: deleted, history left as it is

- Deleted in ab4ec3e. The stand-in mapping (`tests/fixtures/templates/standin/deck-template.yaml`) is the only checked-in mapping and the default export. Nothing had read the old file since e0992dc.
- **By category, it was generic.**
  - Its file name and the template filename it pointed at are generic descriptive words. They are not an organisation's, product's or program's name.
  - Its layout keys are this repo's own layout archetypes, the ones the synthesizer and layout detector use.
  - The rest is placeholder index numbers.
- So I did not rewrite history.
- The tracked tree no longer contains either name. The two earlier deck-export packets name the file; per C4 I can redact those mentions if you want.

## 2. Render without Dagster (7f97230, revision 8)

**What changed.**
- `POST /render/trigger` runs the export in the api process, as a background task.
- The runner is chosen by `RENDER_RUNNER=local|dagster`. When that is unset, the route uses Dagster only if `DAGSTER_HOST` is set. Nothing in `training` sets either, so the deploy runs local.
- The Dagster asset calls the same Dagster-free `render_project`. A test asserts that importing the render modules loads no `dagster` module.
- Job state and output live on disk under `/tmp/wb-exports` (the api is one replica). Jobs expire after 24 h.
- `/render/events/<run_id>` keeps its SSE shape, so the UI is unchanged apart from opening an api-relative download URL. A failed export now streams the contract's problem list.
- `GET /render/file/<run_id>` serves the file **without a token**. The UI opens it with `window.open`, which cannot send one. The run id is a random uuid4, so the URL works like the presigned URLs the Dagster path hands out.
  - Your call if you want it tighter. One option is a short-lived signed URL.
- **Fixed on the way:**
  - The trigger read the project title under the wrong key, so every file was named `Untitled_Project_…`.
  - An unknown format silently became pptx; it is now a 400.
- Tests: 257 → 267 passed.

**The sandbox proof.**
1. **Seed.** A script streamed into the api pod seeded the hydraulics course into the sandbox graph: 7 TargetNodes owned by a probe User.
   - It wrote only wb's own labels and edges from them.
   - Its 4 `DERIVED_FROM` edges point at the hydraulics deck's real Slide nodes, which the sandbox graph already holds under the same content-addressed ids.
   - The image reference is the one the deployed reader hands the editor.
2. **Export.** The script called `POST /render/trigger` through the app's route code. The job finished `SUCCESS`.
3. **Fetch, through the public ingress with no token:**
   - `/render/events/<run_id>` streamed `status SUCCESS` and then `complete` with `download_url /render/file/<run_id>`;
   - `/render/file/<run_id>` returned 200, the pptx content type, and 33,559 bytes;
   - an unknown run id returned 404.
4. **Check.** The fetched deck passes the round-trip check against the golden course with no problems:
   - 8 slides: title, section, concept, concept, section, concept-with-figure, summary, sources;
   - the citations `Sources: hydraulics_fixture.pptx, slides 1, 2` / `Source: …, slide 3` / `Source: …, slide 4`;
   - the reservoir picture on slide 6 only.
5. **Cleanup.** The seeded nodes were deleted afterwards; 0 are left.

**What the proof did not cover.** The trigger step ran with authentication overridden for the probe user, because I have no way to get a token:
- direct grants are off realm-wide;
- the UI login waits on Lane 1's client.

Token checking itself is covered by tests: a missing `authz_id` gets 401, and ownership is checked on 11 routes. Once the client is live, a person signing in and pressing Render runs the same path end to end.

**Two findings for the fixture mode the deploy runs.**
- **Source links depend on the graph.** Assigning sources creates `DERIVED_FROM` only to Slide nodes that exist in the graph. In fixture mode on sandbox this works only because the fixture decks are also ingested there under the same ids. Against a graph without them, assigning sources would silently link nothing. ADR-0060 §4.3, which moves these edges into wb's own records, would remove this dependency.
- **Bare image ids fail in multi-deck mode.** The deploy serves several fixture decks, so image names carry a per-deck prefix. The editor's image references carry it, and they export fine. A synthesizer `{{asset_id}}` without the prefix cannot be resolved there; the export fails, naming the image, rather than dropping it. A fix would pick the deck from the leaf's sources. I have not made it.

## 3. Identity and the client switch

- `authz_id` keying with the hard 401 is live since revision 7.
- The client switch still waits on Lane 1's readback. I check at Sunday 12:00 CT; if it has not arrived, I send Lane 1 a packet naming the Monday-morning deadline.

## Commits

| Commit | What |
|---|---|
| ec12358 | users and drafts keyed on `authz_id` (revision 7) |
| ab4ec3e | old mapping deleted |
| 7f97230 | in-process render, Dagster optional, `/render/file` (revision 8) |
