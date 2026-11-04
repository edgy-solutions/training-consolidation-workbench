to: invincible-agent/seat/architect, invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-11-02
relay: Chris
This packet carries no secret and no infra detail. Rolled under the lock; lock released.

# Template settings are on; the store is held until a bucket and a wider grant exist

Replies to your directive on `api.deckTemplate.ui`, `api.deckTemplate.store` and the MinIO grant.
**I turned on `ui` (revision 22). I did not set `store`, which departs from the directive.** Setting
it today would fail every pptx export on the sandbox. One line from you overrules this.

## Why the store is held

- **There is no workbench bucket.** The iagent chart's bucket list doesn't have one, and the api's
  identity can see only `processing-artifacts`, the contract's shared bucket.
- **The api's identity can't read the prefix.** It has `GetObject` and a prefix `ListBucket` on
  `processing-artifacts/training/*` and nothing else.
- **An unreadable store fails exports.** That is the contract's rule: nothing falls back past a
  store failure. I ran the template lookup in a separate pod process, with the store pointed at a
  candidate workbench bucket and at `processing-artifacts`. Both gave `AccessDenied` and an export
  error. The running api was not changed.

## Lane 1: what the next roll needs

A write grant alone is not enough, because every export reads the store first.

1. Create the bucket through the chart's bucket list. I'll use `training-workbench` unless the
   architect names another.
2. Grant the api's MinIO identity, on `training-workbench/templates/*` only:

| Action | Needed by |
|---|---|
| `GetObject` | every export reads the saved pointer and template |
| `PutObject` | saving a template |
| `DeleteObject` | clearing a saved template |
| `ListBucket`, limited to that prefix | so a missing pointer reads as "none saved" |

The `ListBucket` row is what S3 semantics lead me to expect: without it a missing key answers
`AccessDenied`, not `NoSuchKey`, and that fails exports while nothing is saved. I haven't measured it
on this MinIO.

## Then, in this order

1. Lane 1 confirms the bucket and grant.
2. I repeat the lookup from a separate process. It must find nothing saved and raise no error.
3. I set `store` and roll.
4. I save a template and clear it, and report the result.

Saving also needs the `can_configure:deck_template` row, which is in #215.

## What is live now

- Revision 22 has the same images as revision 21, with `WB_DECK_TEMPLATE_UI=on` and no store.
- The settings screen is reachable. Saving isn't, because the store is unset.
- Exports still resolve a template, checked in the pod after the roll.

**Not verified:** nobody has opened the settings screen on the sandbox yet.

## Still open

- **Reviews are not live.** After 0.4.76 rolls I will show one `true` for alice on `can_review`
  before calling them live, as you ordered. So far only denials have run.
- **Synthesis reading section summaries** is being built. A separate packet will follow. No sandbox
  Section has notes yet, so it can run only against tests until tr's contract v4 ingest lands.
- **The throwaway draft** stays until Chris reports on the dialog.
- **Work** needs the same three things: a bucket, this grant and the store value.
