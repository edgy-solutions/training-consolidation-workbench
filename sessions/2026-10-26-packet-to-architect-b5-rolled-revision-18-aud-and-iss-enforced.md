to: invincible-agent/seat/architect
cc: invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-10-26
relay: Chris
This packet carries no secret and no infra detail.

# b5 rolled: revision 18 enforces aud and iss

Rolled on Lane 1's readback from revision 218
(`ok   training-workbench public, pkce S256, emits authz_id, aud training-workbench`).

- **What rolled:** lane/wb at f99584c, as revision 18. Its images are the digests in the
  work-install packet (api `sha256:0332fd02…`, ui `sha256:f18b5745…`). The roll ran under the
  lock, the gate is green, and the lock is released.
- **What it carries:** b5, plus work-order items 1–3. Generate Outline is a background job with
  progress, and the harmonizer is back on ChainOfThought.
- **Checked live:**
  - The api's accepted aud is `training-workbench`, and its issuer is the public realm URL,
    exact, with no trailing slash.
  - Every protected route answers 401 with no token, and 401 with a forged one. That includes the
    new job route.
- **Not yet checked: a real login.** Direct grants are off, so only a browser login proves the
  accept arm. A session from before 17:26Z needs one refresh (Lane 1's note).
- **Rollback:** branch `lane/wb-pre-b5` (revision 17) stays until Chris confirms a login on
  revision 18. Then I retire it.
