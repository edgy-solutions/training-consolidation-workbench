to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-26
relay: Chris
This packet carries no secret and no infra detail. Hosts are placeholders: `<work-host>` serves
the workbench, `<keycloak-host>` the realm, `<llm-host>` the LiteLLM proxy.

# Work install: images, values, client, LLM, storage, one check each

Chris installs from this packet. Its images (03335a8) are the sandbox's revision 18 (f99584c,
login and Generate Outline confirmed by Chris) plus the template fetch in section 6 (480 tests
pass). They are not rolled to the sandbox yet. The work-order items, in your order:

**1. Answer-only + low reasoning: measured, and not kept (f99584c).** One dry run per mode on the
same deck pair, in the live pod, with the DSPy cache off and nothing saved:

| mode | seconds | sections | slides matched per section | distinct matched | unassigned |
|---|---|---|---|---|---|
| before: ChainOfThought | 176 | 21 | 5–6 | 63 | 100 |
| answer-only, low | 242 | 11 | 6 | 42 | 121 |
| answer-only, medium | 405 | 20 | 2–6 | 55 | 108 |

Low effort titled eight of its eleven sections "Module N". The times swing with load on the shared
LLM host: this morning the same "before" took 7m20s. So no mode is reliably faster, and the
default went back to ChainOfThought. `OUTLINE_REASONING_EFFORT` remains as an opt-in.

**2. Weight labels stripped, terms deduped (3e5aaa6).** Each concept reaches the search once,
without "(primary)" and its siblings.

**3. Generate is a background job (f08d0c3).** It follows the deck-export pattern:
- POST returns a job id;
- the UI polls and shows the step and elapsed seconds;
- the result carries the section count and the unassigned count, and the UI shows both as numbers;
- a job lost to a pod restart reads LOST, with a Retry button.

The synthesis status route now reads the node's own status, so it no longer asks Dagster for
"background_task". A dry run also hit a dropped Neo4j connection after the long LLM call. The
driver now checks idle connections before reusing them (a7dd719).

**Gap note to tr:** sent (f9c537d). It turned out to be wb's own label, which no deployed writer
fills yet. Nothing is asked of tr.

## 1. Images, by digest

Build of lane/wb `03335a8cb5de6ed4455e4519e2de4944bbc1d864` (CI `build-images.yml`, multi-arch amd64 + arm64, tag = full commit sha):

| image | digest |
|---|---|
| `ghcr.io/edgy-solutions/training-consolidation-workbench/api` | `sha256:75008de02d317707ce583d1e27d1854539f7ec37886adcb73c2c78f2e1460c57` |
| `ghcr.io/edgy-solutions/training-consolidation-workbench/ui` | `sha256:e79bf431bc2d094b1fadaedc5cffa5307b8d8c9ec1ab913a0d6156e32be3eea0` |

Set them as `api.image.digest` and `ui.image.digest`; the chart then ignores the tag.

**Check:** `kubectl get pods -l app.kubernetes.io/instance=<release> -o jsonpath='{..imageID}'`
shows both digests above.

## 2. Chart values

Chart `charts/training-workbench` at the same sha. The values that differ from the defaults:

```yaml
global:
  imageRegistry: ghcr.io/edgy-solutions/training-consolidation-workbench
api:
  replicaCount: 1                 # jobs and signed links are in-process; keep one replica
  sourceReader: store             # contract reads: Neo4j + MinIO + Weaviate
  existingSecret: <api secret>    # section 4 lists its keys
  image: {digest: "sha256:75008de02d317707ce583d1e27d1854539f7ec37886adcb73c2c78f2e1460c57"}
  env:
    KEYCLOAK_REALM_URL: <in-cluster realm URL>   # JWKS only; the keys are the same on any host
    NEO4J_URI: bolt://<neo4j service>:7687
    MINIO_ENDPOINT: <minio service>:9000
    MINIO_SECURE: "false"
    BUCKET_NAME: processing-artifacts
    WEAVIATE_URL: http://<weaviate service>:8080
    WB_STORE_WRITES: "on"
    # plus the LLM set, section 4
  ingress:
    enabled: true
    host: <work-host>
    paths: [/source, /draft, /render, /templates, /search, /synthesis, /curriculum, /project, /healthz]
    tls: [...]
ui:
  noAuth: false
  keycloak:
    realmUrl: https://<keycloak-host>/realms/<realm>
    clientId: training-workbench   # the chart default "workbench-app" is wrong; set it
  image: {digest: "sha256:e79bf431bc2d094b1fadaedc5cffa5307b8d8c9ec1ab913a0d6156e32be3eea0"}
  ingress:
    enabled: true
    host: <work-host>             # same host as the api: the UI calls the api same-origin
    paths: [/]
```

The chart derives the api's accepted `aud` (from `ui.keycloak.clientId`) and `iss` (from
`ui.keycloak.realmUrl`). Do not set `KEYCLOAK_AUDIENCE` or `KEYCLOAK_ISSUER` by hand.

**Check:** `curl -sk https://<work-host>/healthz` answers 200, and `https://<work-host>/` redirects
to the Keycloak login.

## 3. Keycloak client `training-workbench`

| setting | value |
|---|---|
| client type | public, no secret |
| flow | standard flow, PKCE S256 required; no implicit flow, no password grant, no service account |
| redirect URI | `https://<work-host>/*` |
| web origin | `https://<work-host>` |
| post-logout redirect | `https://<work-host>/*` |
| roles | `fullScopeAllowed` |

Two mappers, both on the client:

| name | protocolMapper | config |
|---|---|---|
| `authz-id-user` | `oidc-usermodel-attribute-mapper` | `user.attribute` = `claim.name` = `authz_id`, `jsonType.label` String, access/id/userinfo token claim `true` |
| `audience-self` | `oidc-audience-mapper` | `included.client.audience` `training-workbench`, `access.token.claim` `true`, `id.token.claim` `false` |

These match Lane 1's reconcile (#90, #110). The api keys every draft on `authz_id`, never on `sub`.
A user without the `authz_id` attribute gets 401. `aud` may be a list such as
`["training-workbench","account"]`, and the api accepts any list that contains `training-workbench`.

**Check:** log in, copy the access token from the browser, and decode its payload. It must hold
`authz_id` (non-empty), `aud` containing `training-workbench`, and `iss` equal to
`ui.keycloak.realmUrl` exactly, with no trailing slash. If the reconcile job runs at work, its line
reads `ok   training-workbench public, pkce S256, emits authz_id, aud training-workbench`.

## 4. LLM env and the api secret

The api talks to any OpenAI-compatible endpoint. At work that is LiteLLM in front of vLLM:

```yaml
api:
  env:
    LLM_BASE_URL: https://<llm-host>/v1   # setting this selects the OpenAI-compatible path
    LLM_MODEL: <model name as LiteLLM serves it>
    LLM_NUM_CTX: "<model context, tokens>" # sizes the outline merge batches
    # OUTLINE_REASONING_EFFORT: low|medium|high   optional; unset sends no effort
```

The secret named by `api.existingSecret` holds:

| key | what |
|---|---|
| `LLM_API_KEY` | the LiteLLM virtual key |
| `NEO4J_PASSWORD` | Neo4j user `neo4j` (or set `NEO4J_USER` in env) |
| `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | read on bucket `processing-artifacts`, prefix `training/` |
| `WB_ASSET_LINK_KEY` | optional; any random 32+ bytes. Unset, the api makes one per start and open page links stop working at a restart |

Leave `OUTLINE_REASONING_EFFORT` unset. On one deck pair, low effort gave 11 generic sections
against 21 with no effort sent, and saved no reliable time (commit f99584c has the numbers). When
it is set, it travels as `extra_body.reasoning_effort`, which some LiteLLM configs reject.

**Check:** in the api pod run
`python -c "from src.llm_settings import llm_settings as s; x=s(); print(x.provider, x.base_url, x.model, x.num_ctx)"`.
It must print `openai`, the LiteLLM URL, the model and the context, and it never prints the key.
Then select two decks in the UI and press Generate Outline. The button shows each step with its
elapsed time, and the canvas opens with a notice giving the section count and the unassigned count.

## 5. Storage

| what | where | lifetime |
|---|---|---|
| course reads | MinIO bucket `processing-artifacts`, only under `training/`, found through each course's `current.json` | read-only, owned by tr |
| graph | Neo4j: tr's course subgraph (read) and wb's own `Project` / `TargetNode` drafts (write) | durable |
| search | Weaviate `DocumentChunk` (BM25) | read-only |
| deck exports, outline jobs | the api pod's `/tmp` (emptyDir), or `WB_EXPORT_DIR` | lost on a pod restart, swept after 24 h |
| caches (DSPy, NLTK, matplotlib) | `$HOME` = `/tmp`, set by the chart | per pod |
| deck template | `.pptx` at `api.deckTemplate.uri`, cached in `/tmp/wb-template`; mapping in a ConfigMap (section 6) | fetched once per pod |

The root filesystem is read-only. The work log's `Errno 13` on `/home/workbench/.dspy_cache` came
from a deployment that does not set `HOME=/tmp`. This chart sets it.

A pod restart loses running jobs. An outline job then reads LOST and the UI offers Retry, and a
deck export link answers 404 and the user exports again. Nothing in the graph is lost.

**Check:** `kubectl exec <api pod> -- sh -c 'touch $HOME/.w && ls -d /tmp && echo ok'` prints `ok`.
Signed in, `https://<work-host>/source/tree` returns the courses, and a slide's page image opens.

## 6. Deck template

Per your rule, deck export uses one configured template. The template has two parts, and neither
goes in the repo or the chart:

| part | where | set by |
|---|---|---|
| the `.pptx` | object storage, at `api.deckTemplate.uri` = `s3://<bucket>/<key>`. The api fetches it at startup and caches it in `/tmp/wb-template` | Chris uploads it and sets the path |
| the mapping (`deck-template.yaml`: layout and placeholder per role, see `docs/contracts/deck-template.md`) | a ConfigMap named by `api.deckTemplate.mappingConfigMap`, key `deck-template.yaml`, mounted read-only at `/etc/wb/template` | Chris |

```yaml
api:
  deckTemplate:
    uri: s3://<bucket>/<key>.pptx
    mappingConfigMap: <configmap name>
```

```sh
kubectl -n <ns> create configmap <configmap name> --from-file=deck-template.yaml=<local mapping file>
```

- **The api reads the `.pptx` with the MinIO credentials in section 4.** Their policy must allow
  `GetObject` on that key, as well as the `training/` read.
- **Leave `template:` in the mapping as any name.** The api points it at the cached `.pptx`.
- **No URI means the stand-in template.** The api logs that once at startup. A URI that cannot be
  fetched does not fall back: the api logs the error at startup, and each export fails with
  `deck template s3://… could not be fetched`. So a wrongly branded deck never ships silently.
- **The template is read once per pod.** To change it, upload the new `.pptx` and restart the api
  pod: `kubectl rollout restart deploy/<release>-api`.

**Check:**
- `kubectl logs deploy/<release>-api | grep "deck template"` shows one line naming the URI and its
  size, not "stand-in" and not an error.
- `curl -sk https://<work-host>/render/templates` returns `{"templates":["configured"]}`.
- Export a draft as PPTX from the inspector, open it, and its slides use your template's layouts.
