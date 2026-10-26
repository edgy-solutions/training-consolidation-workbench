#!/usr/bin/env python3
"""Pick the image digests a release ships.

A release ships a PAIR (api + ui) built together from ONE commit: the OLDEST ancestor
commit where EVERY component's image build context equals the release commit's context
AND every component has a published image tagged with that full sha.

Builds are not reproducible, so mixing commits per component would ship a pair that
never ran together. One commit means the pair is the one that was rolled and tested.

Why not the release commit's own image: the merge commit on master is rebuilt and gets
new digests, but the bytes that were rolled and tested on the sandbox are the earlier
build of the identical code. Shipping those is what makes "tested" mean something.

Why compute the context ourselves: a commit that touches only docs, sessions/ or the
chart does not change what the image contains, and the Docker ignore rules decide that.
Rules are read at the release sha and applied to every commit compared, so the question
asked is always "does this commit's context equal that one", under one set of rules.

Lives under .github/ so it is outside the api image context.

Exit 0 ok; 3 a component has no published image for its context (JSON still written,
naming the missing component); 1 any other error.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

COMPONENTS = {
    "api": {"context": ".", "ignore": ".dockerignore"},
    "ui": {"context": "frontend", "ignore": "frontend/.dockerignore"},
}
DEFAULT_REGISTRY = "ghcr.io/edgy-solutions/training-consolidation-workbench"
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


class Unexpected(Exception):
    pass


# ---- ignore rules (Docker semantics) -------------------------------------------------

def _glob_to_regex(pat):
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = pat.find("]", i + 2)
            if j < 0:
                out.append(re.escape(c))
                i += 1
            else:
                body = pat[i + 1:j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def parse_rules(text):
    rules = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        neg = line.startswith("!")
        if neg:
            line = line[1:].strip()
        line = line.strip("/")
        if line:
            rules.append((neg, _glob_to_regex(line)))
    return rules


def admitted(rules, path):
    """Last matching rule wins. A rule matches the path or any parent directory."""
    parts = path.split("/")
    prefixes = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    excluded = False
    for neg, rx in rules:
        if any(rx.match(p) for p in prefixes):
            excluded = not neg
    return not excluded


# ---- git -----------------------------------------------------------------------------

def git(args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if r.returncode:
        raise Unexpected(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode("utf-8", errors="surrogateescape")


def context_hash(commit, comp, rules, cwd=None):
    ctx = comp["context"]
    out = git(["ls-tree", "-r", "-z", commit, "--", ctx], cwd)
    entries = []
    for rec in out.split("\0"):
        if not rec:
            continue
        meta, path = rec.split("\t", 1)
        blob = meta.split()[2]
        if ctx != ".":
            path = path[len(ctx) + 1:]
        if admitted(rules, path):
            entries.append((path, blob))
    entries.sort()
    return hashlib.sha256(json.dumps(entries).encode("utf-8", "surrogateescape")).hexdigest()


# ---- registry ------------------------------------------------------------------------

def ghcr_lookup(registry, component, sha):
    """Digest of <registry>/<component>:<sha>, or None if not published."""
    repo = registry.split("/", 1)[1] + "/" + component
    q = urllib.parse.quote(f"repository:{repo}:pull", safe=":/")
    with urllib.request.urlopen(f"https://ghcr.io/token?scope={q}", timeout=30) as r:
        token = json.load(r)["token"]
    req = urllib.request.Request(
        f"https://ghcr.io/v2/{repo}/manifests/{sha}", method="HEAD",
        headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                raise Unexpected(f"{repo}:{sha}: HTTP {r.status}")
            digest = r.headers.get("docker-content-digest")
            if not digest:
                raise Unexpected(f"{repo}:{sha}: no docker-content-digest header")
            return digest
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Unexpected(f"{repo}:{sha}: HTTP {e.code}") from e


# ---- selection -----------------------------------------------------------------------

def select(sha, registry, max_commits, lookup, cwd=None):
    """Return (built_from, components, missing); built_from is None when nothing qualifies."""
    log = git(["log", "--topo-order", f"--max-count={max_commits}", "--format=%H %ct", sha], cwd)
    commits = [(h, int(ct)) for h, ct in (line.split() for line in log.splitlines())]
    equal = None
    for name, comp in COMPONENTS.items():
        rules = parse_rules(git(["show", f"{sha}:{comp['ignore']}"], cwd))
        want = context_hash(sha, comp, rules, cwd)
        ok = {h for h, _ in commits if context_hash(h, comp, rules, cwd) == want}
        equal = ok if equal is None else equal & ok
    # oldest committer date first; on a tie, the one earlier in history (later in topo order)
    cands = sorted(((ct, i, h) for i, (h, ct) in enumerate(commits) if h in equal),
                   key=lambda t: (t[0], -t[1]))
    for _, _, h in cands:
        digests = {n: lookup(registry, n, h) for n in COMPONENTS}
        if all(digests.values()):
            return h, {n: {"image": f"{registry}/{n}", "digest": d, "built_from": h}
                       for n, d in digests.items()}, []
    # Nothing qualifies: report who lacks an image at the newest equal-context commit.
    newest = [h for h, _ in commits if h in equal][0]
    return None, {}, [n for n in COMPONENTS if not lookup(registry, n, newest)]


def main(argv=None, lookup=None, cwd=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    repo_env = os.environ.get("GITHUB_REPOSITORY")
    ap.add_argument("--registry", default=f"ghcr.io/{repo_env.lower()}" if repo_env else DEFAULT_REGISTRY)
    ap.add_argument("--max-commits", type=int, default=400)
    a = ap.parse_args(argv)
    try:
        sha = git(["rev-parse", "--verify", a.sha + "^{commit}"], cwd).strip()
        built_from, found, missing = select(sha, a.registry, a.max_commits, lookup or ghcr_lookup, cwd)
    except Exception as e:  # noqa: BLE001 - any failure is exit 1 with the reason
        print(f"error: {e}", file=sys.stderr)
        return 1
    doc = {"sha": sha, "built_from": built_from, "components": found}
    if missing:
        doc["missing"] = missing
    with open(a.out, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    if missing:
        for c in missing:
            print(f"no published {c} image for this code; wait for build-images on master "
                  "and re-run the release job", file=sys.stderr)
        return 3
    for c, v in found.items():
        print(f"{c}: {v['digest']} (built from {v['built_from']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
