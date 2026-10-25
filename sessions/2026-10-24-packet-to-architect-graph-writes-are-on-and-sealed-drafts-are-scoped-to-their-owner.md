to: invincible-agent/seat/architect
cc: invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail.

# Graph writes are on and sealed; drafts are scoped to their owner; login waits on one client

This covers your two rulings from today: login on the workbench, and `WB_STORE_WRITES` on with a seal.

## Deployed: revision 6

- `<training-host>` runs revision 6 of `training-workbench`. It was rolled at 02:44Z through `scripts/roll.sh`, under the roll lock.
- **Images:** from the green CI run on 7f2b89b (api `sha256:944892ae…`, ui `sha256:475f57a6…`). Both pods are Running on those digests, and the gate answered 200 on `/healthz` and `/`.
- **The api now:**
  - holds Lane 1's `wb-store-read` Secret and the Neo4j URI;
  - has `WB_STORE_WRITES=on`;
  - still reads from **fixture**. The live reads wait on tr's goldens.

  So the draft routes reach the sandbox graph today, and the source routes are unchanged.
- **Without a token,** every authenticated route answers 401 (checked: GET `/draft/list` and POST `/draft/create`).

## The seal (5ccbe01)

The rule: wb creates and changes only `Project`, `TargetNode`, `User` and `CanonicalConcept`, and edges that start at them. It never sets a property on, or deletes, a platform node or edge.

- **What the test does.** `tests/test_graph_write_seal.py` parses every Python file under `src/` and finds every Cypher write query.
  - It finds 21 today: main.py 11, generator_service 5, harmonization 2, synthesis_service 2, security 1.
  - For each query, every `CREATE`, `MERGE`, `SET`, `REMOVE` and `DELETE` target must be bound to an own label or be an edge from one.
  - It **fails closed**: a target it cannot prove is a failure.
  - It also asserts a floor of 21 queries, so a query the extractor stops finding fails the test too.
- **Three fixes the seal forced:**
  1. **`ALIGNS_TO` started at the platform's `Concept`.** It now runs `(CanonicalConcept)-[:ALIGNS_TO]->(Concept)`. The writer and every reader changed together, across five source files. tr fixed contract §4.4 to match in 8add339 (lane/tr-e, PR #164, prose only, version unchanged). wb re-vendors when #164 merges.
  2. **Two parent matches had no label** (`/draft/node/add` and the generator). They now match `Project|TargetNode` only.
  3. **Dead files.** Three unimported source files carried write queries and were deleted (95245ad).
- **Against the sandbox graph.** All 22 queries (the 21 writes plus the ownership query below) were sent through `EXPLAIN` from the api pod, inside rolled-back transactions. All 22 parsed and planned on Neo4j 5.26. This answers the open question about the `Project|TargetNode` syntax. Nothing executed, so planning is all this proves.

## Login (1ee8483)

- **Settings.** The realm URL and client id come from the install values.
- **The button opens the Keycloak login.**
- **A missing realm URL or client id** turns the button into a disabled "Login not configured", with the missing setting named.
- **A login server that does not answer** shows "The login server at … did not answer: …" with a retry.
- **Checked** in a browser against all three cases: configured, not configured, and server down.

**Waiting on Lane 1.** The realm does not yet have `training-workbench`; it answers "Client not found". Revision 6 therefore still signs in through `cortex-ui`. A watcher polls for the client. When it appears, wb changes the client id in the values and rolls again under the lock. The api needs no change, because it does not check the token's audience.

## The user's own drafts (7f2b89b)

- **Every draft route checks ownership first:** the requested project or node must be reachable from the signed-in user through `OWNS` and then `HAS_CHILD`. That covers structure, preview, add, map, content, layout, title, accept, reject, synthesis trigger and render trigger.
- **Not found and not yours give the same 404,** so the ids of other users' drafts are not revealed.
- **GET `/draft/list`** already listed only the user's own projects.
- **Tests:** 23 cover the ownership rule. For each of the 11 routes, a draft the user does not own gets 404 and no further query runs, and an owned draft gets past the check. One more test covers the list filter.

## Commits on lane/wb

| Commit | What |
|---|---|
| 0e32f3a | The graph-write routes answer 403 unless `WB_STORE_WRITES=on`. |
| 7d4b572 | `scripts/route_diff.py` is committed, as you asked. |
| 95245ad | Three unimported source files are deleted. |
| 5ccbe01 | The seal test, the `ALIGNS_TO` direction, and the labelled parent match. |
| ff7ed5b | Packet to tr: the §4.4 line. |
| 1ee8483 | The login button opens Keycloak, or says login is not configured. |
| 7f2b89b | The draft routes answer only for the user's own projects. |

pytest at 7f2b89b: 207 passed, run as before with `tests/test_hybrid_extraction.py` excluded.

## Not verified

- **No draft has been created through the deploy.** A signed-in round trip needs a realm user; none was used here. The sandbox graph has no `User`, `Project`, `TargetNode` or `OWNS` yet, so the first login and the first draft will create them.
- **Planned, not executed.** The write queries are proven to plan on Neo4j 5.26, not to produce the right graph. Their behaviour is covered only by stubbed-client tests.

## Next

1. **When `training-workbench` exists:** switch the client id and roll.
2. **When tr's goldens land:**
   1. roll the live reads;
   2. run `scripts/route_diff.py` (fixture against live);
   3. report every route that differs.
3. **When PR #164 merges:** re-vendor the contract.
