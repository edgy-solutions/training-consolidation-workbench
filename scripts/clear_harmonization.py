"""
Remove the old harmonizer's leftovers from Neo4j: legacy ALIGNS_TO edges and the CanonicalConcepts they orphan.

Why: since contract section 4.7 the doc-tools pass writes ALIGNS_TO as (Concept)-[:ALIGNS_TO {status, ...}]->(CanonicalConcept).
The harmonizer wrote the reversed edge, (CanonicalConcept)-[:ALIGNS_TO]->(Concept) with no status; the pass treats that
as a legacy pin and never aligns that Concept while the edge exists.

Only the legacy shape is touched, so the pass's edges and reviewed decisions survive. Do not run this against
anything but legacy data. Dry run by default; pass --apply to delete.
"""
import sys

from src.storage.neo4j import Neo4jClient

LEGACY_EDGES = "MATCH (cc:CanonicalConcept)-[r:ALIGNS_TO]->(c:Concept) WHERE r.status IS NULL"
# Harmonizer ccs carry no source and no id; only those with no relationships left are removed.
ORPHANS = "MATCH (cc:CanonicalConcept) WHERE cc.source IS NULL AND cc.id IS NULL AND NOT (cc)--()"


def _count(client, match, var):
    result = client.execute_query(f"{match} RETURN count({var}) AS n")
    return result[0]["n"] if result else 0


def clear_harmonization_data(apply=False):
    client = Neo4jClient()

    try:
        edges = _count(client, LEGACY_EDGES, "r")
        print(f"Legacy ALIGNS_TO edges: {edges}")
        if apply:
            client.execute_query(f"{LEGACY_EDGES} DELETE r")
        # Orphans are counted after the edges go; a dry run cannot see ccs the edge delete would free.
        orphans = _count(client, ORPHANS, "cc")
        print(f"Orphaned harmonizer CanonicalConcepts: {orphans}")
        if apply:
            client.execute_query(f"{ORPHANS} DELETE cc")
            print("Applied. Counts now:")
            print(f"  legacy edges: {_count(client, LEGACY_EDGES, 'r')}")
            print(f"  orphaned harmonizer CanonicalConcepts: {_count(client, ORPHANS, 'cc')}")
        else:
            print("Dry run; nothing deleted. Pass --apply to delete.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    clear_harmonization_data(apply="--apply" in sys.argv[1:])
