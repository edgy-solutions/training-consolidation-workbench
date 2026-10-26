to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-25
relay: Chris
This packet carries no secret and no infra detail.

# The render link expires; courses record their decks; image ids always carry the deck prefix

All three are live on sandbox at revision 9 (18b1710).

## 1. The tokenless file route meets all three conditions (f48152c)

| Condition | Before | Now |
|---|---|---|
| Run id ≥ 128 bits from a CSPRNG | uuid4: 122 random bits | `secrets.token_hex(16)`: 128 bits |
| Expiry: 15 min, then 404 | jobs lived 24 h | the link answers 404 fifteen minutes after the export finishes; the job's directory is removed then |
| File bound to its run | already: found only through the run's own record | unchanged; the response also sends `no-store` and `no-referrer` |

- **A second tokenless route, deleted.** `GET /render/download/{filename}` presigned any filename in the published bucket without a token. Those names are guessable: the project title plus 8 hex of the project id. Its frontend client had no callers.
- **Tests** (`tests/test_render_link.py`):
  - the 128-bit draw;
  - the link works inside the TTL, then answers 404 and its directory is gone after it;
  - the file and events routes both answer 404 after expiry;
  - the sweep removes expired runs;
  - a second run cannot reach the first run's file;
  - the deleted route answers 404.
- **On sandbox, through the public ingress with no token:**
  - the export's link returned 200, the pptx type, `no-store` and `no-referrer`;
  - the deleted route and an unknown id returned 404;
  - after 16 minutes the same link returned 404, and so did its events stream.

## 2. Earlier packets

Left as they are, per your ruling.

## 3. Both gaps fixed, with tests (18b1710)

**The course records its decks.**
- A project now records the decks it is built from (`source_deck_ids`), and each node its source slides (`source_slide_ids`). Both are wb's own records.
- Assigning sources first finds each slide's deck, through the reader in fixture mode or the source graph in direct mode. An id it cannot find is a 400 and nothing is written. Before, it silently linked nothing.
- The export reads sources only from those records and resolves them only through the recorded decks' slides. It does not read the graph's links.
- It fails, listing the problems, when the course records no decks, when a recorded deck is not found, or when a source slide is in no recorded deck.
- A test exports the hydraulics course through a fake graph that fails on any Slide query.

**Image ids always carry the deck prefix.**
- Ids are `<deck>--<name>` in every mode. The fixture reader prefixes even when it serves a single deck.
- **The synthesizer was never offered images before.** Now it is offered its source slides' images under prefixed ids and told to copy them verbatim. A bare `{{x}}` it emits anyway is rewritten to the one offered id it stands for.
- Both resolvers refuse a bare id or a foreign prefix. The error names the id: `image 'slide_4_img_0' carries no deck prefix; image ids are '<deck>--<name>'`, or `… names deck prefix '<p>', which is not a deck this course was built from`.

**Proof on sandbox (revision 9).** A script in the api pod drove the real routes, with authentication overridden for a probe user, as before:
1. It seeded a project and 7 nodes with no sources.
2. It assigned sources through `/draft/node/map`:
   - a request carrying an unknown slide id got a 400 naming it;
   - three valid requests recorded exactly the hydraulics deck on the project, and 4 slide refs on the nodes.
3. The export succeeded. The deck, fetched through the ingress, has 8 slides in the golden layout order.
4. A bare `{{slide_4_img_0}}` planted through `/draft/node/content` made the next export fail. The error named the leaf and the id, and no file was written.
5. Everything seeded was deleted; 0 nodes left.

**Not changed:**
- Synthesis still finds a node's sources through the graph's `DERIVED_FROM` edges and reads slide text from the graph. The export does neither now. Moving synthesis onto the records is a small follow-up if you want it.
- In direct mode, a full storage key or presigned URL still resolves without a deck check. Its path already names the deck, but the resolver does not match that against the recorded list.

**Contract.** `docs/contracts/deck-template.md` §3.3 and §3.4 say the same. The mapping format is unchanged, so there is no version bump.

## Numbers

- Tests: 267 → 272 → 289.
- Every new write touches only wb's labels; the seal test is green.
- Every new query passes `EXPLAIN` against the sandbox graph.

## Next: the overnight list

The live-store roll waits on tr's hashes, which have not arrived; tr is on its twenty-deck rerun. The route diff and the write-rule seal test are committed (7d4b572, 5ccbe01). The Sunday 12:00 CT readback check for the client switch is scheduled.

## Commits

| Commit | What |
|---|---|
| f48152c | render link: 128-bit id, 15-minute expiry, presign route deleted |
| 18b1710 | course records its decks; image ids prefixed; resolvers refuse bare ids (revision 9) |
