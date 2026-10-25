"""Every Cypher write query in src/ touches only the workbench's own labels and edges starting at them."""
import pytest

from tests.cypher_seal import extract_write_queries, violations

QUERIES = extract_write_queries()
KNOWN_WRITE_QUERY_COUNT = 21  # counted when the seal was added


def test_extractor_finds_the_write_queries():
    assert len(QUERIES) >= KNOWN_WRITE_QUERY_COUNT


@pytest.mark.parametrize("where,query", QUERIES, ids=[w for w, _ in QUERIES])
def test_write_query_stays_inside_own_labels(where, query):
    assert violations(query) == []


@pytest.mark.parametrize("query", [
    "MATCH (s:Slide {id:$i}) SET s.x = 1",
    "MERGE (c:Concept {name:$n})",
    "MATCH (c:Concept),(cc:CanonicalConcept) MERGE (c)-[:ALIGNS_TO]->(cc)",
    "MATCH (s:Slide) DETACH DELETE s",
    "MATCH (:Course)-[r:HAS_SLIDE]->(s) DELETE r",
    "MATCH (n:TargetNode) SET n:Slide",
    "MATCH (n:{?}) SET n.x=1",
    "MATCH (n:TargetNode) MERGE (n)-[:{?}]->(m:TargetNode)",
    "MATCH (n:TargetNode), (s:Slide) MERGE (n)-[:DERIVED_FROM]-(s)",
    "MATCH (n) SET n.x = 1",
    "MATCH (n:TargetNode) CALL apoc.create.addLabels(n, ['Slide']) YIELD node RETURN node",
    "MATCH (s:Slide) REMOVE s.title",
    "MATCH (p:Project|Slide {id:$id}) CREATE (c:TargetNode) MERGE (p)-[:HAS_CHILD]->(c)",
    "MATCH (p:!TargetNode {id:$id}) SET p.x = 1",
])
def test_analyzer_catches(query):
    assert violations(query) != []


@pytest.mark.parametrize("query", [
    "MATCH (n:TargetNode {id:$id}),(s:Slide {id:$s}) MERGE (n)-[:DERIVED_FROM]->(s)",
    "MATCH (n:TargetNode {id:$id}) DETACH DELETE n",
    "MATCH (n:TargetNode)-[r:SUGGESTED_SOURCE]->(:Slide) DELETE r",
    "MERGE (u:User {id:$id}) ON CREATE SET u.email=$e SET u.last_login=datetime()",
    "MATCH (cc:CanonicalConcept {name:$n}), (c:Concept {name:$c}) MERGE (cc)-[:ALIGNS_TO]->(c)",
    "MATCH (p:Project|TargetNode {id:$id}) CREATE (c:TargetNode) MERGE (p)-[:HAS_CHILD]->(c)",
    "MATCH (t:TargetNode {id:$id}) OPTIONAL MATCH (t)-[r:DERIVED_FROM]->() WITH t, r DELETE r SET t.status = 'draft'",
])
def test_analyzer_passes(query):
    assert violations(query) == []
