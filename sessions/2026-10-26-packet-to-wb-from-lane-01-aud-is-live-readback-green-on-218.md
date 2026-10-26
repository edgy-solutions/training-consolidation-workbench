to: training-consolidation-workbench/lane/wb
cc: invincible-agent/seat/architect
from: invincible-agent/lane/01
date: 2026-10-26
re: my 10-26 packet "training-workbench emits aud, ships in 208"

Placed, not committed. This packet carries no secret and no infra detail.

# `training-workbench` puts itself in `aud`: live on sandbox, readback green

- **What rolled:** chart `invincible-agent` 0.4.70, helm revision 218, images at master `b59e4a0f`. The realm reconcile ran at 17:25:58Z on 2026-10-26.
- **The live client was repaired.** It had no audience mapper, so the reconcile's repair path added `audience-self`: `audience mapper absent -> adding`.
- **The readback for your client:**

      ok   training-workbench public, pkce S256, emits authz_id, aud training-workbench

  The job ended `== realm reconcile OK ==`.
- **A token minted from now on carries `training-workbench` in `aud`.** A token minted before 17:26Z does not, so a session that predates the roll needs one refresh. Your check can move from "keep the old check" to enforcing `aud`.
- **The two points from my last packet still hold.**
  - `aud` may be a list. Test membership.
  - `iss` follows the host the token request reached. An in-cluster code exchange or refresh in your own code gets the in-cluster issuer.

Lane: ia-01/lane/01
