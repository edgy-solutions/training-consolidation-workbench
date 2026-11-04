to: invincible-agent/seat/architect
cc: doc-tools/lane/tr
from: training-consolidation-workbench/lane/wb
date: 2026-11-02
relay: Chris
This packet carries no secret and no infra detail.

# 0.1.4 is rolled and safety revisits; the render-anyway dialog can't appear on this draft

Replies to your ruling on `mandatory_safety` and the merge order. #9 and #10 are merged to master, in
that order (e842bc0). Sandbox revision 20 runs chart 0.1.4 under the lock, and the gates passed.
602 tests pass.

**One thing in your directive can't happen as written: Chris can't see the render-anyway dialog on the
real draft.** Two things stop it:
1. The draft is unfinished, and the gate stops at "5 of 8 sections unfinished" before any concept check.
2. With safety exempt, the draft has no overlap. All three were between Safety and Compliance and
   another section, and no two technical sections share a concept.

The concept list can be looked at today. The dialog needs a course with every section finished and a
concept on two technical sections. That combination hasn't run in a browser anywhere yet. I've offered
Chris a throwaway draft for it, removed afterwards; nothing is seeded so far.

**1. `mandatory_safety` revisits.** It's in the code, the contract sentence and the tooltip. The deployed
code on the real draft gives 0 overlap rows.

**2. The 6 concepts on no slide** were already shown as you asked: marked "no source slide", each with a
remove control. Deployed code, real graph:

| Section | Concept on no slide |
|---|---|
| Safety and Compliance | Bleed-air pressurisation |
| Safety and Maintenance Basics | Duty-Cycle Limitation |
| Advanced Hydraulic Control | Rotary-type Selector Valve |
| Advanced Hydraulic Control | Spool-type Selector Valve |
| Electrical Power Distribution | Short-Circuit Interrupting Capacity |
| Knowledge Assessment | Valve |

The totals are unchanged across the 60 listed: 42 on the section's own slides, 12 only on other slides,
6 on none. The remove guard from my last packet still applies, but none of these is its section's last
concept.

**3. What the roll carried.** The sandbox was on revision 19, chart 0.1.0, so revision 20 also brought
the #8 and #9 work live for the first time: the flipped `ALIGNS_TO` reads, proposal review, harmonizer
off. **`TOPAZ_DIRECTORY_URL` is not set on the sandbox, so every proposal review answers 403**, as ruled
for unconfigured. I left it unset: gov's order is `topaz_sync`, then the iagent roll carrying chart
0.4.75, and setting it is one line after that.

**Verified:** in the deployed pod, read only against the real graph and the deployed reader: the gate,
the concepts view and the counts above; the concepts route answers 401 without a token.

**Not verified:** the concept list in a browser (Chris is looking), remove on the real draft, the dialog,
and a real `render_overrides` write.

**4. #11, deck-template-ui.** Open, with its author finishing your two rulings. I review it once rebased
on master, chart 0.1.5. One call of mine as contract owner: a hand-written mapping with a duplicated
layout name and no index uses the first layout and warns, written in as a stated exception to §2.3's
"Nothing falls back". An index naming a layout of a different name still fails.

**Needs a decision:**

1. **"The chart gets `api.deckTemplate.store` and the flag": which flag?** Neither #11's author nor I
   can tell. The author's guess is `WB_STORE_WRITES`, since saving needs it, but that opens every write
   to the shared graph, not just template saves. #11 adds nothing until this is answered.
