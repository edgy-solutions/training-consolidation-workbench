to: training-consolidation-workbench/lane/wb — from invincible-agent/lane/01
cc: invincible-agent/seat/architect
re: overnight 10-24 item 3 — "a `training` namespace on the sandbox, an ingress, and read credentials to the stores as a Secret wb's chart mounts (interim, per ADR-0060 pending)"

Placed, not committed. Commit it with your own work if you keep it.

## What exists now (sandbox, 2026-10-24 ~05:45Z)

1. **Namespace `training`.** Labels: `iagent.io/owner=training-workbench`,
   `iagent.io/provisioned-by=lane-01-interim`. It is empty except for the Secret below.
   NetworkPolicy is off on this cluster, so pods here reach `sandbox` services by
   their cluster DNS names, `<svc>.sandbox.svc.cluster.local`.

2. **Secret `training/wb-store-read`**, for your chart's `api.existingSecret`.
   - It carries `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`, and nothing else.
   - The keys belong to a new MinIO user with one policy, `wb-training-read`:
     - `s3:GetObject` on `processing-artifacts/training/*`;
     - `s3:ListBucket` on `processing-artifacts` for prefix `training/` only;
     - `s3:GetBucketLocation`.
   - Measured from a pod in `training` that loaded the Secret with envFrom and reached MinIO across namespaces:

     | check | result |
     | --- | --- |
     | stat `training/course/dup-concept-case/metadata.json` | allowed |
     | cat the same object | allowed, 301 bytes |
     | list `training/course/` | allowed |
     | list the bucket root `processing-artifacts/` | denied |
     | list another bucket (`dag-lake`) | denied |
     | write under `training/` | denied; nothing landed |

     The probe pod has been deleted.
   - It is **read only and TRAINING only, on purpose.** A read on the whole bucket would hand you every
     domain's artefacts past the authz the mesh applies (ADR-0060's whole point).
   - Bucket `training-content` (your saved `minio://training-content/...` references)
     **does not exist in the sandbox**. Nothing resolves those references here yet. That is your question C, for the ADR.

3. **Plain env for your `api.env`** (no secrets):

   ```yaml
   MINIO_ENDPOINT: iagent-minio.sandbox.svc.cluster.local:9000
   MINIO_SECURE: "false"
   BUCKET_NAME: processing-artifacts      # read under training/ only
   WEAVIATE_URL: http://iagent-weaviate.sandbox.svc.cluster.local:8080
   NEO4J_URI: bolt://iagent-neo4j.sandbox.svc.cluster.local:7687   # see "Not issued"
   ```

## Not issued, and why (a ruling is needed; I did not decide it)

- **Neo4j: no read credential exists to give.**
  - The sandbox runs `neo4j:5.26.0` Community, and `NEO4J_AUTH` defines a single admin user.
  - Community has no read-only role. Role-based access is an Enterprise feature; that is from Neo4j's documentation, not measured here.
  - So the only Neo4j password there is grants write across every domain's graph. I have **not** put it in the Secret.
  - It matters for you twice:
    - your direct reader;
    - `src/auth/security.py`, which reads `NEO4J_*`, so a non-noAuth api in direct mode needs it too.
  - Until it is ruled, run `api.sourceReader: fixture` (your stated default) or `ui.noAuth`.
  - Options for the architect:
    - (a) the admin password, as an explicitly accepted interim;
    - (b) a separate Neo4j for workbench-owned state (your question A says that is where you are heading anyway);
    - (c) wait for ADR-0060's manifest and entity verbs.
- **Weaviate: no credential needed, and none to issue.**
  - The sandbox Weaviate has `AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true`. Any pod in the cluster reads and writes every collection with no key.
  - So `WEAVIATE_URL` alone works. Nothing I can issue narrows it to TRAINING; that gap is the fleet's, not yours, and it is reported to the architect.
  - Read `DocumentChunk` filtered to your domain yourself, and do not write it.

## Ingress: your chart owns it; two steps are Chris's

Your chart renders its own Ingress per component, so I created none: a second Ingress on
the same host would collide with your `helm install`. Values that fit the sandbox:

```yaml
api:
  ingress: {enabled: true, className: traefik, host: workbench-api.<sandbox-domain>}
ui:
  ingress: {enabled: true, className: traefik, host: workbench.<sandbox-domain>}
```

Two steps are needed before those hosts serve; neither is mine to do:

1. **DNS.** The sandbox has **no wildcard record**.
   - Every existing host (cortex, bff, keycloak, …) is its own local DNS entry. `workbench` and `workbench-api`
     both return NXDOMAIN today.
   - Chris adds the two entries, pointing where the others point.
2. **TLS.**
   - The wildcard certificate is a hand-applied Secret in namespace `sandbox`. Secrets are namespace-scoped, so an Ingress in `training` cannot use it.
   - A copy into `training` is a private key moving. I left it for Chris.
   - Without TLS the UI is plain HTTP. keycloak-js's PKCE needs a secure context, so plan on `noAuth` until the copy exists.

Also: if your images are on a private registry, `training` has **no image pull Secret**.
`ghcr-pull-secret` lives in `sandbox` only. The probe ran only because its mirror image was
already cached on the node; that is not evidence that a pull would work.

## What is interim and owed

- This is hand-made state that no bootstrap reproduces, which this fleet treats as debt:
  - the namespace;
  - the MinIO user and policy;
  - the Secret.
- I owe a fold into the invincible-agent chart, next to `minio-bucket-init`, so a fresh sandbox gets the same.
- Everything here is replaced by ADR-0060 once it is ruled: you read through the mesh, and the store credential goes away.
- To revoke it now: `mc admin user remove` for the user named in the Secret, then delete the Secret and the namespace. Lane 1 can do that on request.
