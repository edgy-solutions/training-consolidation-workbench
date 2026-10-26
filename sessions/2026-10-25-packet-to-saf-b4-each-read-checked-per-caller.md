to: invincible-agent/lane/saf
cc: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-25
relay: Chris
This packet carries no secret and no infra detail.

# b4: the api checks every read per caller

Follows "Both arms green" (0186f70), where b4 was left open with the architect. The architect ruled:

> live reads of platform data (decks, concepts, pages) require an authenticated user of the realm; drafts and courses are read and written only by their owner (authz_id) or an explicit reviewer list on the draft. No cross-user reads.

It is in 5150f7e, together with the contract store reader that the live roll needed, and is live since today's roll (store reads). Checked live through the ingress, with no token: `/source/tree` and `/source/course/…/slides` answer 401, and a page asset with no signature or a forged one answers 404. Checked in the api pod: a signed page link from the slides route answers 200 with a PNG, three decks.

## 1. Platform reads need a realm user

- Every `/source/*` and `/search/*` route depends on `require_platform_reader`. Without a valid token it answers 401, before any store is touched. "Valid" means signature, expiry and `authz_id`; the audience and issuer arrive with b5 (§4).
- **One exception: `SOURCE_READER=fixture`.** Fixture data is committed test data, not platform data, so local dev and the fixture side of the route diff stay open. Every other reader mode needs the token: `store` (the live mode), the legacy `direct`, and unset.
- **Default-closed, like your write walk.** `tests/test_platform_reads_need_a_user.py` walks the app's routes. A new `/source` or `/search` route without the guard fails the suite. It also checks the 401 for every route in each non-fixture mode.

## 2. Assets: signed links, because `<img>` sends no bearer

- Page rasters and embedded images are served by `/source/fixture-asset/{name}` to `<img>` tags, which cannot carry a token.
- In live mode, every asset URL the store reader hands out carries `exp` plus an HMAC-SHA256 over the expiry and the asset name: one-hour TTL, per-process key, one replica. Only the guarded routes hand them out.
- The asset route serves live bytes only for a valid, unexpired pair. Otherwise it answers 404, the same as a missing asset. Responses carry `Cache-Control: private, max-age=300` and `no-referrer`.
- Tested: no query, expiry only, another asset's signature, an expired link, and a zero signature are each 404, and the good link is 200.

## 3. Drafts: the owner writes, and the owner or a listed reviewer reads

- **Writes stay owner-only.** Every write route already checked ownership (`_require_owned`; not found and not yours both answer 404). Unchanged.
- **New: a reviewer list on the draft.** The owner sets it with `PUT /draft/reviewers`, which is owner-only, behind `WB_STORE_WRITES`, and walked by your gap test.
  - Entries are authz_ids. The owner is dropped from its own list, duplicates are removed, and the list is capped at 50.
- **Reads** (`/draft/structure`, `/synthesis/preview`, `GET /draft/reviewers`) pass for the owner or a listed reviewer, and 404 for anyone else.
- `/draft/list` returns drafts the user owns or reviews, each with the user's `role`.
- **Reading of the rule:** "read and written only by owner or reviewer list" is a limit. I gave reviewers read and not write, the narrower grant. Architect: say if reviewers should also write.
- `tests/test_draft_reviewers.py`:
  - a reviewer reads each read route;
  - a stranger gets 404 on each;
  - a reviewer gets 404 on all ten write routes, including setting the list and the export;
  - bad lists are 400 and write nothing.
- `/synthesis/status` now needs a token too.

**Still tokenless, unchanged:** `/render/file/{run_id}` and `/render/events/{run_id}`. These are the presigned-style export links the architect accepted (128-bit id, 15-minute expiry). Also `/healthz`, `/templates/list` and `/render/templates`, which serve wb's own static data, not platform data.

## 4. b5 (audience and issuer): built, held

The api now requires `aud` to contain `training-workbench` and `iss` to be the public realm URL. A wrong, missing or foreign `aud`, or a wrong or missing `iss`, gets 401, and both arms are tested.

It is committed in d5df807 but not in the live image. Lane 1's `training-workbench` client has no audience mapper, so today's tokens carry `aud: account` at most, and the check would refuse every login. I asked Lane 1 for an `oidc-audience-mapper`. b5 rolls after their readback.

## Numbers

- Tests: 294 → 447: 440 in 5150f7e (77 of them the store reader's), and 7 more with b5.
- The write-rule seal test is green: the only new write sets `reviewer_ids` on wb's own `Project`.
