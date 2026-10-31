"""Concept alignment read from doc-tools' normalisation pass (contract §4.7): Concept -> CanonicalConcept."""
from typing import Dict, List, Optional, Protocol


class AlignmentStore(Protocol):
    def display_names(self, names: List[str]) -> Dict[str, str]:
        """name -> canonical name if aligned, else the name itself."""

    def synonyms(self, names: List[str]) -> List[str]:
        """All concept names sharing a CanonicalConcept with any of names, including names."""


class InMemoryAlignmentStore:
    def __init__(self, mapping: Optional[Dict[str, str]] = None):
        self.mapping = dict(mapping or {})

    def display_names(self, names):
        return {n: self.mapping.get(n) or n for n in names}

    def synonyms(self, names):
        out = list(dict.fromkeys(names))
        canon = {self.mapping[n] for n in names if self.mapping.get(n)}
        for k, v in self.mapping.items():
            if v in canon and k not in out:
                out.append(k)
        return out


class Neo4jAlignmentStore:
    def __init__(self, client):
        self.client = client

    def display_names(self, names):
        names = list(names)
        if not names:
            return {}
        rows = self.client.execute_query(
            """
            MATCH (c:Concept) WHERE c.name IN $names
            OPTIONAL MATCH (c)-[:ALIGNS_TO]->(cc:CanonicalConcept)
            RETURN c.name as name, coalesce(cc.name, c.name) as display
            """,
            {"names": names},
        )
        out = {n: n for n in names}
        for r in rows:
            out[r["name"]] = r["display"]
        return out

    def synonyms(self, names):
        names = list(dict.fromkeys(names))
        if not names:
            return []
        rows = self.client.execute_query(
            """
            MATCH (c:Concept) WHERE c.name IN $names
            OPTIONAL MATCH (c)-[:ALIGNS_TO]->(cc:CanonicalConcept)<-[:ALIGNS_TO]-(syn:Concept)
            RETURN collect(DISTINCT syn.name) as syns
            """,
            {"names": names},
        )
        out = list(names)
        for r in rows:
            for n in r["syns"]:
                if n and n not in out:
                    out.append(n)
        return out


# Proposal review (contract §4.7): doc-tools' pass writes PROPOSED_ALIGNS_TO; the workbench only sets the decision.
# 100 rows = 50 pairs x 2 directions; conflict proposals ride along.
PROPOSALS_QUERY = """
    MATCH (co:Course {id: $cid})-[:HAS_SLIDE|HAS_CHILD]->(:Slide)-[:TEACHES]->(t:Concept)
    WITH DISTINCT t
    MATCH (c:Concept)-[p:PROPOSED_ALIGNS_TO]->(cc:CanonicalConcept)
    WHERE p.status = 'open' AND (c = t OR (t)-[:ALIGNS_TO]->(cc))
    WITH DISTINCT c, p, cc
    OPTIONAL MATCH (s:Slide)-[:TEACHES]->(c)
    WHERE EXISTS { MATCH (s)-[:TEACHES]->(:Concept)-[:ALIGNS_TO]->(cc) }
    WITH c, p, cc, count(DISTINCT s) AS shared
    OPTIONAL MATCH (m:Concept)-[:ALIGNS_TO]->(cc)
    WITH c, p, cc, shared, collect(DISTINCT m.name)[..10] AS members
    RETURN c.id AS concept_id, c.name AS concept, coalesce(cc.id, cc.name) AS canonical_id, cc.name AS canonical,
           members, p.confidence AS confidence, p.method AS method, p.evidence AS evidence, p.cos AS cos, shared
    ORDER BY shared DESC, confidence DESC, coalesce(cos, -2.0) DESC, concept_id, canonical_id
    LIMIT 100
    """

REVIEW_QUERY = """
    MATCH (c:Concept {id: $concept_id})-[p:PROPOSED_ALIGNS_TO]->(cc:CanonicalConcept)
    WHERE coalesce(cc.id, cc.name) = $canonical_id AND p.status = 'open'
    SET p.status = $status, p.reviewed_by = $uid, p.reviewed_at = $at
    RETURN count(p) AS n
    """
