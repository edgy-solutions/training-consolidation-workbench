"""Compare every read route between two api bases (A = fixture, B = live).

usage: uv run --no-project python -I scripts/route_diff.py BASE_A BASE_B OUT_DIR
Writes OUT_DIR/summary.md (one row per route) and OUT_DIR/<n>.json (A, B, diffs) per differing route.
URLs are compared by presence only (hosts and presigned queries differ by design).
"""
import json, ssl, sys, urllib.parse, urllib.request
from pathlib import Path

A, B, OUT = sys.argv[1].rstrip("/"), sys.argv[2].rstrip("/"), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
URL_KEYS = {"s3_url", "url", "presigned"}


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300].decode(errors="replace")
    except Exception as e:  # timeouts, refused, bad JSON
        return -1, repr(e)[:300]


def norm(v, key=None):
    if key in URL_KEYS:
        return "<url>" if v else v
    if isinstance(v, dict):
        if all(isinstance(k, str) and k.startswith(("http://", "https://")) for k in v) and v:
            return {"<url>": len(v)}  # resolve-image-urls map
        return {k: norm(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [norm(x) for x in v]
    return v


def diffs(a, b, path="$", out=None):
    out = [] if out is None else out
    if len(out) >= 20:
        return out
    if type(a) is not type(b):
        out.append(f"{path}: {type(a).__name__} vs {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'B' if k not in a else 'A'}")
            else:
                diffs(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: {len(a)} items vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: {json.dumps(a)[:80]} vs {json.dumps(b)[:80]}")
    return out


q = urllib.parse.quote
routes = [("GET", "/source/filters", None), ("GET", "/source/tree", None)]
st, tree = call(A, "GET", "/source/tree")
courses = [c for g in (tree if st == 200 else []) for c in g["children"]]
for d in sorted({c.get("engineering_discipline") for c in courses} - {None}):
    routes.append(("GET", f"/source/tree?engineering_discipline={q(d)}", None))
slide_ids, concepts = [], set()
for c in courses:
    cid = q(c["id"], safe="")
    routes += [("GET", f"/source/course/{cid}/slides", None), ("GET", f"/source/course/{cid}/sections", None),
               ("GET", f"/source/embedded-images/{cid}", None)]
    s, rows = call(A, "GET", f"/source/course/{cid}/slides")
    for r in rows if s == 200 else []:
        slide_ids.append(r["id"])
        concepts.update(x["name"] for x in r.get("concepts") or [])
routes += [("GET", f"/source/slide/{q(s, safe='')}", None) for s in slide_ids]
routes.append(("POST", "/source/embedded-images-for-slides", slide_ids[:40]))
sample = sorted(concepts)[:15]
for n in sample:
    routes += [("GET", f"/source/graph/concept/{q(n, safe='')}", None), ("GET", f"/source/heatmap/{q(n, safe='')}", None),
               ("GET", f"/search/concepts?q={q(n[:4])}", None)]
st, filt = call(A, "GET", "/source/filters")
searches = [{"query": "", "filters": {}}] + [{"query": n, "filters": {}} for n in sample[:5]]
for o in (filt.get("origins", []) if st == 200 else []):
    searches.append({"query": "", "filters": {"origin": o}})
routes += [("POST", "/source/search", s) for s in searches]

rows, same = [], 0
for i, (m, p, body) in enumerate(routes):
    (sa, ja), (sb, jb) = call(A, m, p, body), call(B, m, p, body)
    d = [f"status {sa} vs {sb}"] if sa != sb else []
    if sa == sb == 200:
        d += diffs(norm(ja), norm(jb))
    elif sa == sb and ja != jb:
        d.append("error bodies differ")
    if not d:
        same += 1
        continue
    label = p if body is None else f"{p} {json.dumps(body)[:60]}"
    (OUT / f"{i}.json").write_text(json.dumps({"route": label, "A": ja, "B": jb, "diffs": d}, indent=1)[:200000])
    rows.append(f"| {i} | `{m} {label}` | {d[0]} | {len(d)}{'+' if len(d) >= 20 else ''} |")

(OUT / "summary.md").write_text(
    f"A={A}\nB={B}\n\n{len(routes)} calls; {same} identical, {len(rows)} differ.\n\n"
    "| # | route | first difference | count |\n|---|---|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
print(f"{len(routes)} calls; {same} identical; {len(rows)} differ -> {OUT / 'summary.md'}")
