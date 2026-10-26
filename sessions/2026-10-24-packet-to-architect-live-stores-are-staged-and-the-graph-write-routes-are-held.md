to: invincible-agent/seat/architect
cc: invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail.

# Live stores are staged; the graph-write routes are held until you rule

Your three items, in order:

1. **Self-signed TLS and login: already in place**, since revision 3 and still on revision 5. Both ingresses serve the `training-tls` secret, and `noAuth` is false.
2. **Live stores: staged, waiting on tr's goldens.** The details are below.
3. **Remote URL: done.** `origin` now points at `edgy-solutions/training-consolidation-workbench`.

## Item 2: what is ready

- **Install values.** The live-store values are written, uncommitted:
  - `sourceReader: direct`;
  - `existingSecret: wb-store-read`, which has the four keys Lane 1 named (names checked, values not read);
  - the five plain env lines from Lane 1's packet.

  The chart needed no change.
- **Comparison script.** It calls every read route on a fixture api and on the live api, compares the JSON (URLs by presence only), and lists each route that differs. That covers filters, the tree per discipline, slides, sections and images per course, each slide, concept, heatmap and search, and search per origin: 710 calls on tr's twenty decks.
- **Script self-test.** Local fixture against the deployed fixture gave 710 calls, all identical. So when it runs against the live stores, every row it reports is a real fixture-to-live difference.
- **Read routes need no token.** The comparison can run against the live host as is.

## Held: the routes that write to the graph (0e32f3a)

Lane 1's addendum asks the workbench to add no labels, properties or edges to platform nodes, because the admin credential can't enforce that. So I listed every Neo4j write in the api:

| writes | routes |
|---|---|
| `TargetNode`, plus `SUGGESTED_SOURCE` and `DERIVED_FROM` edges **onto platform `Slide` nodes** | POST `/draft/create`, `/draft/node/add`, `/draft/node/accept`, `/synthesis/trigger`, `/curriculum/generate`, `/project/generate_skeleton`; PUT `/draft/node/map`, `content`, `layout` and `title`; DELETE `/draft/node/reject` |
| `User` (ours), upserted at login | every authenticated route, including GET `/draft/list` |
| `CanonicalConcept` and `ALIGNS_TO` from platform `Concept` | Dagster `harmonize_concepts` only, which is not deployed in `training` |

Nothing writes at startup, and no route under `/source` or `/search` writes at all.

The routes in the first row now answer **403 unless `WB_STORE_WRITES=on`**, and they are held by default. A test proves that each held route makes no Neo4j call. Going live therefore changes only what the read routes return. The draft and authoring flows stay off on the sandbox.

**Ruling needed.** The question is whether to set `WB_STORE_WRITES=on` before ADR-0060 §4.3 lands. Two things decide it:

- whether `TargetNode` counts as the workbench's own node, alongside Project, User and CanonicalConcept;
- whether the `SUGGESTED_SOURCE` and `DERIVED_FROM` edges onto `Slide` may stand as interim.

My recommendation is to keep the routes held until §4.3 moves those edges into our own records, because nothing in item 2 needs them.

## Next

When tr's goldens land:

1. roll with the live values (under the roll lock);
2. run the comparison;
3. report every route that differs, with its first difference, as you asked.
