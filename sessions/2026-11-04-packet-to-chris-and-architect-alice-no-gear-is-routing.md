# Packet: wb → Chris, architect — alice sees no gear: the ingress, not the flag or Topaz

From: training-consolidation-workbench/lane/wb · 2026-11-04 · sandbox rev 24 (chart 0.1.6)

## The three questions

**1. Is WB_DECK_TEMPLATE_UI on in 0.1.6's values?** Yes.
- Rolled values (`helm get values`, rev 24): `api.deckTemplate.ui: true`, `store` set.
- Pod: `WB_DECK_TEMPLATE_UI=on`; `WB_STORE_WRITES`, `DECK_TEMPLATE_STORE`, `TOPAZ_DIRECTORY_URL` set;
  `ALIGNMENT_REVIEW_SUBJECT=alignment`; `AUTHZ_CLAIM` unset, so the subject id is the token's `authz_id` claim.

**2. Is alice in training-admins and alignment-reviewers per Topaz?** Yes for `alice@example.com`; no for
`alice@company.com`. Topaz holds both user objects. The answers, from the pod, are the same check call the api makes
(`POST /api/v3/directory/check`, subject_type `user`):

| subject_id | check | Topaz answer |
|---|---|---|
| alice@example.com | group:training-admins#member | `{'check': True}` |
| alice@example.com | group:alignment-reviewers#member | `{'check': True}` |
| alice@example.com | capability:can_configure:deck_template#can_invoke | `{'check': True}` |
| alice@example.com | capability:can_review:alignment#can_invoke | `{'check': True}` |
| alice@company.com | all four of the above | `{'check': False}` |

The capability object `can_configure:deck_template` exists, so the 0.4.78 sync has landed in this Topaz.
Still open: which of the two ids alice's token carries as `authz_id`. If it's `alice@company.com`, she's
denied everywhere. Once (3) below is fixed, the settings screen will settle it: its state carries `can_configure`
for the signed-in user.

**3. Where does a reviewer see that they can review?** Nowhere yet. The api has `GET /alignment/proposals` and
`POST /alignment/proposals/review` (Topaz `can_review`), but no UI calls them; the review UI is a carried item.
So nothing on screen can show `can_review` today.

## Why there is no gear

The gear asks `GET /settings/deck-template/enabled`. The ingress routes only these prefixes to the api:
`/source /draft /render /templates /search /synthesis /curriculum /project /healthz`. `/settings` isn't one,
so the UI's catch-all `/` answers it with `index.html` (200, text/html). `res.data.enabled` is then undefined
and the gear stays hidden. The api logged no `/settings` request in the last 24 hours.

`/alignment` is missing from the same list, so the review routes are unreachable through the gate as well.

## What turns it on

Add `/settings` and `/alignment` to `api.ingress.paths` in the deployment's values and roll.
- Sandbox: a values-only roll (rev 25, same images). It's reversible, and rev 24 is the rollback.
- Work: the same two paths in work's values.
- Chart: the `api.ingress.paths` comment in `values.yaml` lists the nine prefixes; it should list all eleven.
  A small commit, with no version bump needed for a comment.

After the roll, sign in as alice: the gear shows, and the settings screen says whether she can save.
`can_review` stays invisible until the review UI exists.
