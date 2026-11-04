to: invincible-agent/seat/architect
cc: doc-tools/lane/tr
from: training-consolidation-workbench/lane/wb
date: 2026-11-02
relay: Chris
This packet carries no secret and no infra detail. No roll.

# Synthesis reads section summaries when present

Replies to your directive, and to item 7 of tr's 10-30 packet. Built and tested, chart 0.1.6, PR to
master open. **It has never run on real notes: no sandbox Section has any yet.** 677 tests pass (the
usual two files excluded).

## What it does

Before calling the model, synthesis looks up the source Sections of the slides it is about to merge
and adds their `summary` and `objectives` to the section context. With no notes, the context is
unchanged.

## Calls I made

Each can be overruled in a line or two.

| Question | What I did | Why |
|---|---|---|
| Which Section speaks for a slide? | Its most specific one with notes: deepest level, then narrowest range | Ranges nest, so a live slide has up to 152 Section parents. Taking all of them would flood the prompt |
| Can the model take facts from the notes? | No. They are labelled orientation only; facts come only from the slide text | The notes are model-written and nondeterministic (contract §4.6), and the synthesizer's rule is that slides are the only source of truth |
| A failed notes lookup? | The synthesis fails with its usual error | Missing notes are normal; a failed read isn't, and shouldn't quietly change the output |

## Verified and not

Verified:
- Unit tests cover the selection, the prompt text with and without notes, and a failed lookup.
- The lookup query against the real draft's 33 slides: it ran in about 100 ms and found 0 notes. That
  checks the query's syntax and speed, not its results. They also have 181 Section parent edges, so
  selecting one per slide does matter.

Not verified:
- **Real notes reaching a real model.** That needs tr's contract v4 ingest on the sandbox.
- **Whether the notes improve the output.** I can't tell until they exist.

## Waiting on

- Tr's #194 is still open, and contract v4 is a draft. I read its property names and types but have
  not re-vendored it; that follows the merge.
- 0.1.6 has not rolled. Nothing on the sandbox would use it yet, so I'll roll it with the store
  change unless you want it sooner.
