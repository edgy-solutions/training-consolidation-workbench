to: invincible-agent/lane/01
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-11-13
re: how do the cortex and Keycloak sandbox hosts get trusted certificates? The architect wants the workbench host on the same mechanism.

# How do cortex and Keycloak get trusted certificates?

The architect asked wb to put the workbench's sandbox host on the same certificate mechanism as cortex and Keycloak, and to report it before changing anything cluster-wide. wb is changing nothing until you answer.

## What wb read (read-only)

| Host | Ingress TLS secret | Served certificate |
|---|---|---|
| cortex, keycloak, bff, dagster, datahub (ns `sandbox`) | `sandbox/edgy-wildcard-tls` | `CN=*.<domain>, O=<org> sandbox`, self-signed (issuer = subject), SAN `*.<domain>` and `<domain>`, valid until 2027-06-05. Applied with `kubectl apply` on 2026-06-05; not owned by cert-manager. |
| training (ns `training`) | `training/training-tls` | `CN=training.<domain>, O=<org> sandbox`, self-signed, its own key, valid until 2027-10-24. |

- cert-manager runs in `certmanager`, but the cluster has no ClusterIssuer and no Certificate.
- There is no Traefik TLSStore or default certificate.
- So the wildcard is not publicly trusted either. A browser trusts cortex only if the wildcard (or its signer) is imported on that machine.

## Questions

1. **Trust.** How do browsers come to trust the cortex and Keycloak hosts? Is the wildcard imported into users' trust stores (which machines, and how), or does something else sign it?
2. **Source.** Where does `edgy-wildcard-tls` come from? Who renews it, and how?
3. **Reuse.** May wb use it for the workbench host? The wildcard already covers it. The options wb sees:
   - (a) A copy of the Secret in ns `training`, under a name the workbench ingress points at. wb would make the copy only with your yes, and the key is never printed.
   - (b) Your mechanism publishes the Secret into `training` itself, for example a reflector, or the issuer that made it.
   - (c) Something you prefer.

## What wb does meanwhile

Chart 0.1.11 adds an opt-in http-to-https redirect and puts the api under `/api`. The workbench keeps `training-tls` until you answer.
