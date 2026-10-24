"""Business units that differ only in case or whitespace form one tree group, on both tree paths."""
from src.workbench.source_routes import _course_tree


def _course(i, bu):
    return {"id": f"c{i}", "title": f"Course {i}", "business_unit": bu, "discipline": None}


def test_case_and_whitespace_variants_share_a_group():
    tree = _course_tree([
        _course(1, "Industrial Pumps"), _course(2, "industrial  pumps "),
        _course(3, "Industrial Pumps"), _course(4, None), _course(5, "  "),
    ])
    assert [(g["name"], [c["id"] for c in g["children"]]) for g in tree] == [
        ("Industrial Pumps", ["c1", "c2", "c3"]),  # most frequent spelling
        ("Uncategorized", ["c4", "c5"]),
    ]


def test_direct_tree_route_groups_the_same_way(monkeypatch):
    monkeypatch.setenv("SOURCE_READER", "direct")
    from fastapi.testclient import TestClient
    from src.workbench import main

    rows = [
        {"bu": "Avionics", "id": "a", "title": "A", "engineering_discipline": "Electrical",
         "filename": "a.pptx", "version": "1.0"},
        {"bu": "avionics", "id": "b", "title": "B", "engineering_discipline": None,
         "filename": None, "version": None},
        {"bu": None, "id": "c", "title": "C", "engineering_discipline": None,
         "filename": None, "version": None},
    ]
    monkeypatch.setattr(main.neo4j_client, "execute_query", lambda q, p=None: rows, raising=False)
    tree = TestClient(main.app).get("/source/tree").json()
    assert [(g["name"], [c["id"] for c in g["children"]]) for g in tree] == [
        ("Avionics", ["a", "b"]), ("Uncategorized", ["c"]),
    ]
    assert tree[0]["children"][0] == {
        "id": "a", "name": "A", "type": "Course", "engineering_discipline": "Electrical",
        "filename": "a.pptx", "version": "1.0", "has_children": True,
    }
