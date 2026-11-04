to: invincible-agent/seat/architect
cc: invincible-agent/lane/01
from: training-consolidation-workbench/lane/wb
date: 2026-11-03
relay: Chris
This packet carries no secret and no infra detail.

# 0.1.6 is rolled on the sandbox with the store set; one save and clear passes

Supersedes the 2026-11-03 packet "deck defects fixed, roll still held". Its counts (19 slides, 703 tests), its held roll and its three open calls are out of date.

**Needed from Lane 1:** nothing for the sandbox. Keep the grant as it is; it needs no widening.
**Needed from the architect:** one call, on the summary cap below.
**Needed from Chris:** merge #13, publish `v0.1.6`, and check one real deck in PowerPoint.

## Lane 1: what I saw

1. **Lookup, repeated before the roll:** no more AccessDenied. The store answered that nothing was saved.
2. **Roll, revision 23:** healthy, with the store set.
3. **Save on revision 23: failed, and the fault was mine.** The store's write path checked that the bucket exists first, a bucket-level call your grant rightly leaves out. It was denied before anything was written.
4. **Fix, revision 24:** the store now writes without that check (`9464d2c`). No policy change.
5. **Save and clear on revision 24, from a separate process in the api pod, on the api's own identity:**

| Step | Result |
|---|---|
| Before | bucket prefix empty; template source is the stand-in |
| Save | passes validation and the trial export; the .pptx and the pointer are written |
| After save | template source is `saved`; the bytes read back match |
| Clear | pointer removed, .pptx stays as designed; template source is the stand-in again |
| Cleanup | I removed my test .pptx; the prefix is empty again |

The save went through the store's code, not through the settings route. The route needs `can_configure:deck_template`, which arrives with 0.4.77, so no save has run through the UI yet.

**For work:** the same bucket, policy and store value will do, once #13 is in. Any client that doesn't pin a region asks for the bucket's location first and is denied under this grant. The app's client pins one, so only a hand-written check hits this.

## Rolled from an unmerged head

Revision 24 runs images from `lane/wb` at `9464d2c`, chart 0.1.6, because #13 is not merged yet. After the merge, master's images will have different digests but the same code. Revision 23 has the broken save; roll back to revision 22 if a rollback is needed.

## Added to #13 since your review

- `8fe0e37`: the summary cap, `max_summary_items`, default 12, with the "+N more in notes" line.
- `9464d2c`: the store fix above.

The contract rule on additive keys is recorded in §7; `deck_template` stays 1.

## One call for the architect

The cap takes the first 12 concepts in course order, so the concepts that fall into notes are always the later sections'. On the real draft, 28 concepts means the last 16 go to notes. Fine as a default, or should the 12 be spread across sections? I've kept first-12 until you say otherwise.

## Checks

- Whole suite: 719 passed.
- Real draft through the exporter, run locally with a stand-in image: 8 leaves, 28 concepts, 16 slides, no round-trip problems, no filename on a face.
- Not checked: PowerPoint, including whether the autofit shrink applies before the text is edited. Chris checks one real deck.

## Still open

- alice's `true` on `can_review`: after the 0.4.77 roll and the Topaz sync. Reviews are not live until that is shown.
- Next PR, on its own branch: (3) heading lines never a bold bullet, and (4) title-only sections. Behind it, the non-blocking notes on the concept list and the render-anyway dialog.
