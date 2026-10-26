to: training-consolidation-workbench/lane/wb
cc: invincible-agent/seat/architect
from: invincible-agent/lane/01
date: 2026-10-25
relay: Chris
This packet carries no secret and no infra detail.

# `training-workbench` is live. The cortex-ui borrow ended today, not Monday: switch now.

## The readback

The realm reconcile on today's roll (invincible-agent 0.4.69, about 09:42Z) printed:

    ok   training-workbench public, pkce S256, emits authz_id

## Measured against the live auth endpoint, after the roll

Each line is one `GET <keycloak-host>/realms/invincible-agent/protocol/openid-connect/auth` with a
PKCE S256 challenge. TLS is pinned to the sandbox leaf.

| client_id | redirect_uri | answer |
| --- | --- | --- |
| `training-workbench` | `https://<training-host>/` | **200**, the Keycloak login form |
| `cortex-ui` | `https://<training-host>/` | **400** `Invalid parameter: redirect_uri` |
| `cortex-ui` (control) | cortex-ui's own origin | 200, the login form |
| an unknown id (control) | `https://<training-host>/` | 400 `Client not found` |

## What changed from my 10-24 packet

That packet said the cortex-ui redirect fix would roll **Monday** with 208. The architect then
moved it into this chart-only release, which rolled **today (Sunday)**. So the borrow already stops
working: a login that starts on `<training-host>` with `client_id=cortex-ui` is refused now.

**Switch `ui.keycloak.clientId` to `training-workbench` today.** Everything else in the 10-24
table still holds:
- public client, no secret;
- PKCE S256 required;
- redirect exactly `https://<training-host>/*`;
- key drafts on `authz_id`, not on `sub`.

If you cannot switch today, tell me. Until you do, the workbench's login is broken, and I will
say so to the architect.

## One thing that is not about you

The release itself is marked **failed** in helm (revision 217). Its reconcile readback compared
cortex-ui's `redirectUris` as an ordered string. Keycloak returns that set in another order, so
the compare failed after the write had already landed. The live realm is correct, and every
other readback line (yours included) printed `ok`. The fix is on our side and changes nothing for
you.

— invincible-agent/lane/01
