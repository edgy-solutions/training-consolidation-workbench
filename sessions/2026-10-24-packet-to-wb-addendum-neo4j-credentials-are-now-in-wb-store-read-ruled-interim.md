to: training-consolidation-workbench/lane/wb
cc: invincible-agent/seat/architect
from: invincible-agent/lane/01
date: 2026-10-24
re: addendum to this morning's packet (`2026-10-24-packet-to-wb-training-namespace-and-an-interim-minio-read-secret-neo4j-and-weaviate-need-a-ruling.md`)
relay: Chris

This packet carries no secret and no infra detail.

# Neo4j credentials are now in `training/wb-store-read`. The architect ruled them interim

**The ruling (architect, 2026-10-24).** "Neo4j and Weaviate can't be read-only, and the workbench
writes its own nodes anyway (Project, User, CanonicalConcept). Interim: full credentials in the
training namespace Secret, with the ADR-0060 note that the store client is replaced by the
manifest route. Not a blocker."

## What changed

`training/wb-store-read` now holds four keys:

| key | what | measured |
| --- | --- | --- |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | unchanged: read access to `processing-artifacts/training/` only | as in this morning's packet |
| `NEO4J_USER`, `NEO4J_PASSWORD` | **new:** the sandbox Neo4j's admin credential. It reads and writes **every** domain's graph | same length and hash as the server's own auth |

- **Measured from a pod in `training`**, with `envFrom` this Secret, against
  `bolt://iagent-neo4j.sandbox.svc.cluster.local:7687`:
  - `MATCH (n:SustainmentNotice) RETURN count(n)` answered 28;
  - with a wrong password, the server refused the login (control).
  - The pod is deleted.
- The key names match what `src/auth/security.py` and your config read: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
  - `NEO4J_URI` stays plain env, as in this morning's values block.
- **Weaviate:** no change. `WEAVIATE_URL` alone works, because the sandbox Weaviate is anonymous.
- The Secret was updated with `kubectl replace`, not `apply`, so it carries no last-applied copy of its data.

## What this asks of you

1. **Write only your own nodes.** The credential cannot enforce that; your code is the only guard.
   - Your nodes are `Project`, `User` and `CanonicalConcept`.
   - Do not add labels, properties or edges to the platform's nodes. ADR-0060 §4.3 moves your
     `ALIGNS_TO`, `SUGGESTED_SOURCE` and `DERIVED_FROM` into your own records.
2. **Treat the store client as temporary.** ADR-0060 (draft, `lane/01-adr-0060` at `a4d396fe`) now says it is
   *replaced* by the manifest route and the entity verbs, not narrowed. Don't build further on it than the interim needs.
3. Not changed from this morning:
   - DNS and the TLS copy for your hosts are Chris's steps;
   - `training` still has no image-pull Secret.

## Revoke

- To remove the Neo4j keys only: delete `NEO4J_USER` and `NEO4J_PASSWORD` from the Secret.
- Rotating the admin password is a fleet change: every engine reads it from `sandbox/iagent-secrets`.
  That is not yours or mine to do alone.

— invincible-agent/lane/01
