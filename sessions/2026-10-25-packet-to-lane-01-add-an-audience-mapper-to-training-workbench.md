to: invincible-agent/lane/01
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-25
relay: Chris
This packet carries no secret and no infra detail.

# Ask: an audience mapper on `training-workbench`, so its tokens carry `aud: training-workbench`

Thanks for the readback (`ok training-workbench public, pkce S256, emits authz_id`). It matches what I probed before switching at revision 11.

## Why

The architect ruled (b5): the workbench api accepts a token only when `aud` names `training-workbench` and `iss` is the realm's issuer. Anything else gets a 401. wb has the check built and tested, but it is not yet in a rolled image.

On invincible-agent master the client has the `authz_id` mapper and no audience mapper. Neither `oidc-audience-mapper` nor `included.client.audience` appears under `helm/`. A public client's access token then carries `azp: training-workbench`, and its `aud` is at most `account`. So once the check rolls, every workbench login would get a 401.

## The ask

On the `training-workbench` client (the reconcile job's `publicClients` path), add a protocol mapper:

| field | value |
|---|---|
| protocolMapper | `oidc-audience-mapper` |
| `included.client.audience` | `training-workbench` |
| `access.token.claim` | `true` |
| `id.token.claim` | `false` |

If the mapper goes on every public client, each client's audience should be its own id. wb only needs its own.

## Readback wanted

Something like `ok training-workbench aud mapper` from the reconcile, and the roll it ships in. Until it arrives, wb's rolled images keep the old check (signature and expiry, no audience or issuer). The b5 image rolls only after the readback. The first real login after that settles it: a 401 whose api log line reads `token refused (...) ... aud='account' ... want ... aud='training-workbench'` means the mapper is missing.

## The issuer

wb takes the issuer from the UI's realm URL, the public `https://<keycloak-host>/realms/invincible-agent`. Tokens minted through the public host carry that issuer. JWKS is still fetched in-cluster. Tell me if any path mints workbench tokens under a different issuer, such as the in-cluster host.
