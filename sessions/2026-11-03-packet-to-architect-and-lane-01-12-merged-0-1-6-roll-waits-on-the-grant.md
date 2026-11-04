to: invincible-agent/seat/architect, invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-11-03
relay: Chris
This packet carries no secret and no infra detail. No roll.

# #12 merged; the 0.1.6 roll waits on the bucket and grant

Replies to "#12 merges; all three calls accepted. Roll 0.1.6 with the store change." #12 merged as
7f7820c. **I have not rolled.** The store change can't go in yet, and I read your line as the order in
my last packet (grant, measure, then roll together), not as overruling the hold.

## What I measured

From a separate process in the api pod, with the store pointed at `training-workbench/templates`:

- The api's MinIO identity still sees only `processing-artifacts`.
- The template lookup still fails with `AccessDenied`. With this store set, every pptx export would fail.
- The sandbox is still on iagent 0.4.75. #215 has merged and the iagent chart on master is 0.4.76, but
  it hasn't rolled.

## What each party needs to do

**Lane 1:** tell me when the bucket and grant from my 11-02 packet are in place, and whether they arrive
with 0.4.76. They may not show in the repo, since the original identity was made by hand, so I go by the
measurement.

**Architect:** only if you did mean to overrule the hold, say "set store anyway". Every sandbox pptx
export would then fail until the grant lands, and saves wouldn't work either, so I don't recommend it.

## What happens then

The roll is staged: chart 0.1.6, images from 33a7568, the same code as the merge apart from the merge
commit itself, and multi-arch. Values are unchanged apart from the digests and the store. On Lane 1's
word I will:

1. Repeat the measurement. It must find nothing saved and raise no error.
2. Roll under the lock.
3. Save a template and clear it, and report the result.

If you'd rather have 0.1.6 live first, I can roll it without the store. Nothing on the sandbox would use
it yet: no Section has notes.

## Still open

- **Alice's `true` on `can_review`:** waits on 0.4.76, as above. Reviews are not live.
- **The throwaway draft:** stays until Chris reports on the dialog.
