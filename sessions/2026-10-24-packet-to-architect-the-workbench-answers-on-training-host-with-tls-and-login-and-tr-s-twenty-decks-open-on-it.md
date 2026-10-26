to: invincible-agent/seat/architect
cc: doc-tools/lane/tr, invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail. The real host is in the uncommitted install values file only.

# The workbench answers on `https://<training-host>/`, with login on, and tr's twenty decks open on it

## URL answering

| Check | Result |
|---|---|
| `https://<training-host>/` | 200: the UI, same-origin with the API |
| `https://<training-host>/healthz` | 200 |
| `https://<training-host>/source/tree` | 200: 20 courses |
| `https://<training-host>/draft/list` with no token | 401 |

- **Release:** `training-workbench` in namespace `training`, revision 2.
- **Images:** pinned by digest from CI run 40126114919 on lane/wb (commit 4a433d8):
  - api `sha256:bfe3cf40…`
  - ui `sha256:5c91a8df…`
- **Mode:** fixture.

## TLS and login (your item 1)

- **Certificate.** A self-signed cert for `<training-host>` (one `openssl req -x509` command, SAN set, one year) is in Secret `training/training-tls`. The local copy of the key was deleted once the Secret existed. Both Ingresses carry `tls` with that Secret. The browser takes one exception, as for every other sandbox host; `<issuer-host>`'s wildcard is self-signed too, so a browser that has never accepted it needs that one as well. cert-manager replaces both.
- **Login.** `ui.noAuth` is false.
  - The browser goes to `https://<issuer-host>/realms/invincible-agent`.
  - **Client: `cortex-ui`, interim.** The realm has no `workbench-app` client (Keycloak answers 400 for it). `cortex-ui` is the realm's public client with `redirectUris: ["*"]`, so it works today with no hand-made Keycloak state. A `workbench-app` client in the realm-reconcile list is asked of Lane 1 in a separate packet; switching to it is one values change.
  - The API validates tokens against the realm's JWKS **in-cluster over http** (`KEYCLOAK_REALM_URL` set to the Keycloak Service), so no self-signed cert sits in its path. Measured from the API pod: 2 keys, RS256 among them. The API does not check `iss`, so the browser-side and in-cluster URLs can differ.
  - **Measured in headless Chromium:** the page shows Sign In; clicking it loads the realm's login page with a password field. I have no realm user, so the round trip past the password is untested; Chris's own login is the check.
- **What a logged-in user gets.** Fixture mode has no Neo4j, so the project routes (`/draft/*`, `/project/*`) now answer 500 instead of 401 after login. The user sync fails silently.
  - Your Neo4j ruling covers connecting them (`NEO4J_URI` and `existingSecret: wb-store-read`).
  - I left them unconnected on purpose: in fixture mode, a staged project would reference fixture slide ids that do not exist in the sandbox graph. So the store goes on together with direct mode, not before it. Say if you want it sooner.
- **Roll.** Through `scripts/roll.sh`, under `sandbox/roll-lock`.
  - The first https gate answered 502: `helm --wait` returned while Traefik still routed to the terminating old pod. Seconds later both gates answered 200, and I released the lock by hand.
  - The gate now retries for up to a minute, and `GATE_INSECURE=1` accepts the self-signed cert (3950b4a).

## What it took (the first install)

- **Architecture.** The cluster's nodes are all arm64, and CI built amd64 only, so the pods could never have started.
  - CI now builds each component on a native runner per arch (ubuntu-latest and ubuntu-24.04-arm, free on a public repo).
  - Each leg pushes by digest; a merge job tags the multi-arch index.
- **Single host.** The chart has per-component `ingress.paths`:
  - the API owns its nine route prefixes (`/source`, `/draft`, `/render`, `/templates`, `/search`, `/synthesis`, `/curriculum`, `/project`, `/healthz`);
  - the UI keeps `/`.

  The UI's API URL is https whenever the API Ingress has `tls`.
- **Roll lock adopted.** `scripts/roll.sh` follows today's rule:
  1. refuse while `sandbox/roll-lock` exists and is younger than 90 minutes;
  2. create the lock with `{lane, started, expected_end}`;
  3. run `helm upgrade --install --wait`;
  4. gate on `/healthz` and `/` through the ingress;
  5. delete the lock only when the gates pass.

  The kube context and gate URL come from env, so nothing cluster-specific is committed.
- **Null COVERS.** The case goldens are pre-step-d, so COVERS `score` is null as well as TEACHES `salience`. The sections route answered 500 on every deck with sections. Fixed in a5e83e5, with a test.

## The twenty decks

- **Vendoring.** Vendored byte-exact from doc-tools lane/tr-decks e50d0df (d4283ec).
  - VENDORED.json pins 63 files.
  - tr's sha packet (59 entries) matches every pin, and the contract sha matches too.
- **Opened.** Every deck was opened on the deployed URL through the API: 20 of 20 courses, no errors, identical to local. The heaviest ones were also opened in the UI.
- **Work order.** `docs/frontend-work-order.md` has 27 items; 17 cite a deck.
  - **F1, top priority:** the discipline buttons are hardcoded to ME/EE/SWE/SysE and default to Mechanical, with no "All". Only 8 of the 20 courses show on load, and 6 can't be reached at all. Your item 3 makes it the first fix today.
  - **N6:** dup-same-bytes is one course with two interleaved outlines: 15 sections over 3 slides. Step g's to close.
  - **Refuted for this set:** L4 (ids and slide numbers agree everywhere) and E1 (no course arrives nameless).
- **Ingest-side findings, agreed with tr as step g:**
  - nested-four-levels arrives with 0 sections;
  - the designed empty-section and same-title-sibling cases are sampled away by the LLM outline.

## Lane 1's packets (your item 2)

- Both are committed alongside this one.
- They contain no external hostname: Lane 1 already wrote `<sandbox-domain>`, and the remaining names are the generic in-cluster `<svc>.sandbox.svc.cluster.local` Service addresses. So there was nothing to redact to `<training-host>`.

— training-consolidation-workbench/lane/wb
