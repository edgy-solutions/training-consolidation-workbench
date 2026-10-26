"""Finds Cypher write queries in src/ and checks them against the graph-write seal.

The workbench creates and changes only its own labels (OWN) and edges whose start node is one of
those. It never sets a property on, adds or removes a label on, or deletes a platform node or edge.
The analyzer is a simplified Cypher reader that fails closed: anything it cannot resolve is a violation.
"""
import ast
import re
from pathlib import Path

OWN = {"Project", "TargetNode", "User", "CanonicalConcept"}
PLACEHOLDER = "{?}"
_SENT = "\x00"

SRC = Path(__file__).resolve().parent.parent / "src"


# ---------------------------------------------------------------- extraction

_STRING_RE = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")


def _strip_strings(q):
    q = _STRING_RE.sub("''", q)
    return re.sub(r"//[^\n]*", "", q)


_WRITE_RES = [
    re.compile(r"(?<![\w.$:`])(?i:CREATE|MERGE)\s*\("),
    re.compile(r"(?<![\w.$:`])CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT|INDEX|FULLTEXT|RANGE|TEXT|POINT|VECTOR|LOOKUP|DATABASE)\b"),
    re.compile(r"(?<![\w.$:`])SET\s+[\w`]+\s*(?:\.|:|\+?=)"),
    re.compile(r"(?<![\w.$:`])(?:DETACH\s+)?DELETE\s+[\w`]+"),
    re.compile(r"(?<![\w.$:`])REMOVE\s+[\w`]+\s*[.:]"),
]


def is_write_query(text):
    s = _strip_strings(text)
    if "(" not in s:
        return False
    return any(r.search(s) for r in _WRITE_RES)


def _text(node):
    """String value of a Constant, f-string or + chain, or None if the node is not string-like."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
            else:
                out.append(PLACEHOLDER)
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        if left is None and right is None:
            return None
        return (left if left is not None else PLACEHOLDER) + (right if right is not None else PLACEHOLDER)
    return None


def extract_write_queries(root=SRC):
    """Returns [("src/path.py:line", query)] for every Cypher write query under root."""
    root = Path(root)
    found = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        docstrings = {id(n.value) for n in ast.walk(tree)
                      if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        stack = [tree]
        while stack:
            node = stack.pop()
            for child in ast.iter_child_nodes(node):
                if id(child) in docstrings:
                    continue
                text = _text(child) if isinstance(child, (ast.Constant, ast.JoinedStr, ast.BinOp)) else None
                if text is not None:
                    if is_write_query(text):
                        found.append((f"{path.relative_to(root.parent).as_posix()}:{child.lineno}", text))
                    continue
                stack.append(child)
    return sorted(found)


# ---------------------------------------------------------------- analysis

_KW = re.compile(
    r"(?<![\w.$:`])(OPTIONAL\s+MATCH|MATCH|ON\s+CREATE\s+SET|ON\s+MATCH\s+SET|CREATE|MERGE|DETACH\s+DELETE|DELETE|SET|"
    r"REMOVE|WITH|UNWIND|WHERE|RETURN|ORDER\s+BY|CALL|FOREACH|LIMIT|SKIP|UNION|YIELD)\b",
    re.I,
)
_PATTERN_TOKEN = re.compile(r"(?P<node>\((?P<ncontent>[^()]*)\))|(?P<rel>(?P<left><)?-\s*(?:\[(?P<rcontent>[^\]]*)\])?\s*-(?P<right>>)?)")


def _prepare(q):
    q = q.replace(PLACEHOLDER, _SENT)
    q = _strip_strings(q)
    prev = None
    while prev != q:
        prev = q
        q = re.sub(r"\{[^{}]*\}", "{}", q)
    return q


def _clauses(q):
    """Splits on keywords at bracket depth 0 into [(KEYWORD, body)]."""
    depth, depths = 0, []
    for ch in q:
        if ch in "([{":
            depth += 1
        depths.append(depth)
        if ch in ")]}":
            depth -= 1
    marks = [m for m in _KW.finditer(q) if depths[m.start()] == 0]
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(q)
        out.append((re.sub(r"\s+", " ", m.group(1).upper()), q[m.end():end].strip()))
    return out


def _split_top(s):
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts]


class _Scope:
    def __init__(self):
        self.vars = {}  # name -> ("node", set(labels)) | ("rel", start_is_own) | ("value",)

    def copy(self):
        s = _Scope()
        s.vars = dict(self.vars)
        return s

    def own_target(self, name):
        b = self.vars.get(name)
        if b is None:
            return False, f"variable '{name}' is not bound to a node or relationship (cannot verify)"
        if b[0] == "node":
            if b[1] and b[1] <= OWN:
                return True, ""
            return False, f"'{name}' is not an own node (labels: {sorted(b[1]) or 'none'})"
        if b[0] == "rel":
            if b[1]:
                return True, ""
            return False, f"'{name}' is a relationship that does not start at an own node"
        return False, f"'{name}' is not a node or relationship (cannot verify)"


def _parse_node(content):
    c = content.strip()
    m = re.match(r"[\w`]*", c)
    var = m.group(0).strip("`") or None
    labels = [lab.strip("`") for expr in re.findall(r":\s*([^\s:{}]+)", c[m.end():]) for lab in re.split(r"[|&]", expr)]  # A|B, A&B: every part must be own
    return var, labels, _SENT in c


def _patterns(body, scope, creating, problems, kw):
    """Binds variables from the patterns in body; when creating, checks creations and edge starts."""
    for part in _split_top(body):
        prev = None  # (var, is_own)
        pending = None  # (rel var, arrow_left, arrow_right, text)
        for tok in _PATTERN_TOKEN.finditer(part):
            if tok.group("node") is not None:
                var, labels, sent = _parse_node(tok.group("ncontent"))
                if sent:
                    problems.append(f"{kw}: placeholder in a label or variable position (cannot verify): {tok.group(0)}")
                existing = scope.vars.get(var) if var else None
                bound = existing is not None
                labs = (existing[1] | set(labels)) if bound and existing[0] == "node" else set(labels)
                if creating and not bound:
                    if not labs:
                        problems.append(f"{kw}: creates an unlabeled node (cannot verify): {tok.group(0)}")
                    elif not labs <= OWN:
                        problems.append(f"{kw}: creates a node with platform label(s) {sorted(labs - OWN)}")
                is_node_var = not (bound and existing[0] != "node")
                if var and is_node_var:
                    scope.vars[var] = ("node", labs)
                cur = (var, bool(labs) and labs <= OWN and is_node_var)
                if pending is not None and prev is not None:
                    rvar, left, right, rtext = pending
                    if left == right:
                        if creating:
                            problems.append(f"{kw}: undirected relationship in a write: {rtext}")
                        start_own = False
                    elif left:
                        start_own = cur[1]
                    else:
                        start_own = prev[1]
                    if creating and left != right and not start_own:
                        problems.append(f"{kw}: relationship {rtext} starts at a platform node")
                    if rvar:
                        scope.vars[rvar] = ("rel", start_own)
                pending = None
                prev = cur
            else:
                inner = tok.group("rcontent") or ""
                if _SENT in inner:
                    problems.append(f"{kw}: placeholder in a relationship type (cannot verify): {tok.group(0)}")
                rvar = re.match(r"\s*([\w`]*)", inner).group(1).strip("`") or None
                pending = (rvar, bool(tok.group("left")), bool(tok.group("right")), tok.group(0))


def _set_items(body, scope, problems, kw, remove=False):
    for item in _split_top(body):
        if _SENT in item.split("=")[0]:
            problems.append(f"{kw}: placeholder in a target (cannot verify): {item}")
            continue
        m = re.match(r"([\w`]+)\s*(\.\s*[\w`]+|\+?=|(?::\s*[\w`]+)+)", item)
        if not m:
            problems.append(f"{kw}: cannot parse target (cannot verify): {item}")
            continue
        name = m.group(1).strip("`")
        ok, why = scope.own_target(name)
        if not ok:
            problems.append(f"{kw}: {why}")
        if m.group(2).startswith(":"):
            for lab in re.findall(r":\s*([\w`]+)", m.group(2)):
                if lab.strip("`") not in OWN:
                    problems.append(f"{kw}: {'removes' if remove else 'adds'} platform label {lab}")


def _run(q, scope, problems):
    for kw, body in _clauses(q):
        if kw in ("MATCH", "OPTIONAL MATCH"):
            _patterns(body, scope, False, problems, kw)
        elif kw in ("CREATE", "MERGE"):
            if not body.startswith("(") and not re.match(r"[\w`]+\s*=\s*\(", body):
                problems.append(f"{kw}: not a node or path pattern (cannot verify): {body[:40]}")
            else:
                _patterns(body, scope, True, problems, kw)
        elif kw in ("SET", "ON CREATE SET", "ON MATCH SET"):
            _set_items(body, scope, problems, kw)
        elif kw == "REMOVE":
            _set_items(body, scope, problems, kw, remove=True)
        elif kw in ("DELETE", "DETACH DELETE"):
            for item in _split_top(body):
                name = item.strip("` ")
                if not re.fullmatch(r"\w+", name):
                    problems.append(f"{kw}: deletes an expression (cannot verify): {item}")
                    continue
                ok, why = scope.own_target(name)
                if not ok:
                    problems.append(f"{kw}: {why}")
        elif kw == "WITH":
            body = re.sub(r"^DISTINCT\s+", "", body, flags=re.I)
            if body.strip() == "*":
                continue
            new = {}
            for item in _split_top(body):
                m = re.match(r"(.+?)\s+AS\s+([\w`]+)$", item, re.I | re.S)
                if m:
                    expr, alias = m.group(1).strip(), m.group(2).strip("`")
                    new[alias] = scope.vars.get(expr, ("value",)) if re.fullmatch(r"\w+", expr) else ("value",)
                elif re.fullmatch(r"\w+", item):
                    new[item] = scope.vars.get(item, ("value",))
            scope.vars = new
        elif kw == "UNWIND":
            m = re.search(r"\bAS\s+([\w`]+)\s*$", body, re.I)
            if m:
                scope.vars[m.group(1).strip("`")] = ("value",)
        elif kw == "FOREACH":
            m = re.match(r"\(\s*(\w+)\s+IN\s+.*?\|(.*)\)\s*$", body, re.S | re.I)
            if not m:
                problems.append(f"FOREACH: cannot parse (cannot verify): {body[:40]}")
            else:
                inner = scope.copy()
                inner.vars[m.group(1)] = ("value",)
                _run(m.group(2), inner, problems)
        elif kw == "CALL":
            problems.append(f"CALL in a write query (cannot verify): {body[:40]}")
        elif kw == "UNION":
            scope.vars = {}


def violations(query):
    """Returns the reasons a write query breaks the seal; an empty list means it passes."""
    problems = []
    if re.search(r"\bapoc\.", query, re.I):
        problems.append("apoc procedure in a write query (cannot verify)")
    _run(_prepare(query), _Scope(), problems)
    return problems
