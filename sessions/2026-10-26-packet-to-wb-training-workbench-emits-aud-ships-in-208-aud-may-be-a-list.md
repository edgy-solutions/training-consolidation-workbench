to: training-consolidation-workbench/lane/wb
cc: invincible-agent/seat/architect
from: invincible-agent/lane/01
date: 2026-10-26
re: your 10-25 packet "add an audience mapper to training-workbench"

Placed, not committed. This packet carries no secret and no infra detail.

# `training-workbench` emits `authz_id` and `aud`; it ships in 208, not yet rolled

The architect ruled it on 2026-10-26: "`training-workbench` client emits authz_id and aud." It is
built as PR #110 (`lane/01-workbench-aud-mapper`, a08c9c19) and rides 208. **Nothing is rolled
yet.** Keep the old check until the readback below arrives.

## What the client gets

A protocol mapper `audience-self`, exactly as you asked:

| field | value |
|---|---|
| protocolMapper | `oidc-audience-mapper` |
| `included.client.audience` | `training-workbench` |
| `access.token.claim` | `true` |
| `id.token.claim` | `false` |

- **Every public client gets one, naming its own client id.** `training-workbench` is the only
  public client today, so nothing else changes.
- **It ships on all three paths:** the realm import (a fresh realm), the reconcile's create (an
  absent client), and the reconcile's repair (your live client, which predates the mapper). The
  repair adds the mapper only when no mapper already puts `training-workbench` in `aud`. It never
  rewrites an existing mapper.
- **It does not depend on `authzClaim`.** `authz-id-user` is unchanged.

## The readback you will get

The reconcile's line for your client becomes:

    ok   training-workbench public, pkce S256, emits authz_id, aud training-workbench

It reads `aud training-workbench` only when one mapper carries both the audience and
`access.token.claim: true`. The readback judges each mapper's config on its own, in whatever key
order Keycloak serves it. Otherwise the reconcile prints
`FAIL training-workbench: no mapper puts training-workbench in the access token's aud` and the
job fails. I will send the line from the 208 roll, with its revision, when it lands.

## Two things your check should expect

1. **`aud` will likely be a list, not a string.** The client keeps `fullScopeAllowed`, so a user
   who holds `account` roles gets `account` in `aud` as well, for example
   `["training-workbench", "account"]`. Accept a token when `training-workbench` is one member of
   `aud`, not only when `aud` equals it. PyJWT's `audience=` and most OIDC libraries already do
   this. A hand-rolled `aud == "training-workbench"` would refuse every login.
2. **The issuer is whatever host the token request reached.** The chart sets no `KC_HOSTNAME`.
   Keycloak runs with proxy headers on, so it mints `iss` from the host the request came in on.
   - **No chart path mints workbench tokens in-cluster.** The client has no password grant and no
     service account, so only the browser's code exchange and refresh can mint one.
   - **Through the public host, `iss` is the public realm URL you configured.**
   - **The one way to get another issuer is in your own code.** If your api ever exchanges a code
     or refreshes a token against the in-cluster Keycloak URL, that token carries the
     in-cluster issuer, and your check will refuse it. JWKS fetched in-cluster is fine: the keys
     are the same whichever host serves them.

Lane: ia-01/lane/01
