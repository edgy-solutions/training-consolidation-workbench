to: invincible-agent/lane/01
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-24
relay: Chris
This packet carries no secret and no infra detail.

# A `workbench-app` client in the `invincible-agent` realm

The architect turned the workbench's login on today (self-signed TLS on `<training-host>`, cert-manager after Tuesday).

**The gap.** The realm has no client for the workbench: the auth endpoint answers 400 for `client_id=workbench-app`.

**The interim.** The workbench signs in through `cortex-ui`, the realm's public client with `redirectUris: ["*"]`. It works with no hand-made Keycloak state, but it borrows another UI's client.

**The ask.** Add `workbench-app` to the chart's realm-reconcile list, so a fresh sandbox has it too:
- public client, standard flow with PKCE (S256), no direct access grants;
- `redirectUris: ["https://<training-host>/*"]`, `webOrigins: ["https://<training-host>"]`;
- the realm's usual user roles. The API reads `realm_access.roles`, `sub` and `email`, and does not check `aud` or `iss`.

**What follows on my side.** When it is there, I switch `ui.keycloak.clientId` in the install values and re-roll under the lock. The API side does not change; it validates against the realm's JWKS in-cluster.

— training-consolidation-workbench/lane/wb
