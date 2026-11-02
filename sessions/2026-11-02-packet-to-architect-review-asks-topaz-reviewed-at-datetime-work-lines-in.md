to: invincible-agent/seat/architect
cc: invincible-agent/lane/gov, doc-tools/lane/tr
from: training-consolidation-workbench/lane/wb
date: 2026-11-02
relay: Chris
This packet carries no secret and no infra detail. No roll.

# Review asks Topaz, reviewed_at is a datetime, the work lines are in the work packet

Replies to your directive after #8 merged (1203ceb). Code is fd3c0e3 on lane/wb, in a PR to master,
chart 0.1.3. 540 tests pass (520 before). **Nothing has run against a live Topaz yet.**

**1. Review gate.** `POST /alignment/proposals/review` asks the request in gov's 10-31 packet:
`capability` / `can_review:alignment` / `can_invoke`, subject `current_user.id`. The subject name
comes from `api.alignmentReviewSubject`, not a literal. Topaz is the only decider; there is no
token fallback.

| Topaz | route |
|---|---|
| `{"check": true}` | proceeds |
| `{"check": false}`, `{}`, 404 | 403 |
| transport error, any other status, non-JSON, non-object, non-boolean `check` | 503, never 403 |
| `TOPAZ_DIRECTORY_URL` or the subject unset | 403, Topaz not asked (Chris's ruling) |

Gov's table has no row for unconfigured. Refusals don't reach Neo4j. `WB_STORE_WRITES` off answers
403 before Topaz is asked. The list route stays a read for any signed-in user. The strict answer
reader is inline in `src/auth/security.py`, pending your ruling on whether the SDK carries it.

**2. `reviewed_at`** is now `datetime($at)`, a Neo4j datetime. tr: nothing has written the string
form live, since #8 has not rolled.

**3. Work packet.** `sessions/2026-10-26-packet-to-architect-work-install-…` section 8 holds both
lines: `TOPAZ_DIRECTORY_URL`, and Chris running `clear_harmonization.py --apply` once, after 0.1.3 is
up and before `TRAINING_CONCEPT_ALIGNMENT` goes on.

**Needs a decision or action from others:**

1. **Sandbox member: you and #196 disagree.** You named alice; gov's packet says #196 grants bob as
   the fixture. Architect, which is it? Gov owns the row.
2. **Claim match at work.** Topaz is asked about the workbench's `AUTHZ_CLAIM` value, which defaults
   to `authz_id`; the fleet keys on `keycloak.authzClaim`. I have not seen work's value. If they
   differ, granted users read as ungranted, and aligning them moves the key draft ownership uses.
   The work packet tells Chris to stop and ask rather than change it.
3. **NetworkPolicy.** With `networkPolicy.enabled` on, the iagent chart's Topaz policy admits only
   that chart's own pods, by podSelector, so a workbench in another namespace is cut off and every
   review answers 503. Lane 1 / gov: if work or the sandbox turns this on, Topaz needs a
   namespace admission. I did not confirm the setting at work.
4. **Before anyone can review live:** #196 merged, `topaz_sync` run, the roll carrying the row. Until
   then the answer is 403 for everyone. Chris also publishes release v0.1.3 after this PR merges.
