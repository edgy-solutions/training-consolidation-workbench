# Packet: wb → architect, Chris — 0.1.7 released and live; the next wb block is the review UI (needs your call)

From: training-consolidation-workbench/lane/wb · 2026-11-05

## Where things stand

- **v0.1.7 is published** (#16 merged as 8386df4; the release run is green). It pins api `sha256:67a52b48…` and ui
  `sha256:c168250c…`, built from ba473a8. It carries #14 (one bold subtitle, section bodies), #15 (concept
  list and render-anyway notes), the even summary split with a plain "+N more in notes" line, and the
  `/settings` and `/alignment` ingress note.
- **Sandbox rev 26 runs exactly v0.1.7.** Rollback is rev 25 (0.1.6 images plus the two ingress paths).
- **alice on 0.1.7:** Chris confirmed the gear and the template dialog. The api logged both `/settings` calls at 200
  and no decider warnings, so her token maps to the granted Topaz id (`alice@example.com`).
- **Work:** installs `--version 0.1.7`. Contract §8 now has a Routing note: if work's api shares the UI's host, its
  `api.ingress.paths` must list `/settings` and `/alignment`; an api on its own host with `/` needs nothing. Work
  also needs its mapping to map a section `body`, or section dividers get no slide and land in `render_overrides`
  as `skipped_sections`.

## The open gap: nowhere on screen can a reviewer review

The api has `GET /alignment/proposals?course_id=` (signed-in reader) and `POST /alignment/proposals/review` (Topaz
`can_review:alignment`, plus `WB_STORE_WRITES`). No UI calls either, and nothing tells the UI whether the user can
review. There is also no data to review on the sandbox: the graph has no `CanonicalConcept` nodes and no
`ALIGNS_TO`/`PROPOSED_ALIGNS_TO` edges, so the list is empty for every course.

A minimal block, for your yes, no or changes:
1. **api:** `GET /alignment/review-access` → `{"can_review": bool}`. It's the same decider call as the review route.
   Unconfigured is `false`; decider unavailable is a 503, as on the review route.
2. **UI:** when `can_review` is true, the top bar shows a "Review" entry next to the gear. It opens a panel of the
   current course's open proposals (concept → canonical, with the shared-slide count the query already returns)
   and Accept / Reject on each. A 403 or 503 answer shows in the panel and is never retried silently.
3. **No entry when false.** A non-reviewer sees nothing new. The only on-screen answer to "can I review?" is the
   entry's presence, the same way the gear answers for templates.

Questions:
- (a) Is this the right shape, or should review live in the existing concept list (per concept, inline)?
- (b) Who writes `PROPOSED_ALIGNS_TO` on the sandbox? Without it the panel can only be tested on fixtures.
- (c) Same PR for the api route and the UI, chart 0.1.8? Or hold until proposals exist on the sandbox?

## Also waiting (not wb's to start)

- tr: the "structural" concept flag (title/agenda/layout slides with no body text). Once tr puts the flag in its
  contract, wb hides those concepts from the concept list and the summary by default. That's a small follow-up
  here.
- Shrink-on-overflow is still unverified in PowerPoint; LibreOffice shows no overflow (carried).
