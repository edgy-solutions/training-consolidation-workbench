"""Workbench-owned concept alignment (Concept -> CanonicalConcept)."""
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
