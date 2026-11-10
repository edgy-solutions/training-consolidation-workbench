# Changelog

Chart releases, newest first. A release is the GitHub release `v<version>`; earlier ones are described there.

## 0.1.10

- **Image placeholders load when the UI and the api are on different hosts.** 0.1.8 resolved `{{<deck>--<name>}}` to
  an api-relative `/source/fixture-asset/...` link, which the browser fetched from the UI's host and got `index.html`.
  The link now carries the api's host (`VITE_API_URL`), as the asset tray's links already did.
- **Synthesis is told which concepts the section teaches.** The section's concepts, as the deck will list them, go
  into the synthesis context as a focus line, each with the other names it goes by: the slides' related terms, its
  canonical name and its aligned synonyms. The slide text stays the only source of facts. A section with no concepts
  synthesizes as before.
- **"listed, not covered" in the concepts panel.** When a section has synthesized text, a concept the deck lists that
  neither it nor any of its other names appears in is flagged. It is a string check and never blocks a render or an
  export.
- **The concepts panel says what concepts do.** One line: they pick the section's slides, are listed on the summary and
  in the notes, and steer synthesis.

## 0.1.9

- **Alignment review UI, behind `api.alignmentReviewUi`** (renders `WB_ALIGNMENT_REVIEW_UI=on`; default off). A Review
  entry in the top bar opens a per-course list of open alignment proposals with Accept and Reject. The entry shows
  only when the flag is on and Topaz grants the user `can_review:<alignmentReviewSubject>`. The new
  `GET /alignment/review-access` answers `{enabled, can_review, writes_enabled}`. With the flag off it asks nothing of
  the decider; if the decider is unavailable it answers 503. Deciding needs `WB_STORE_WRITES=on`. Without it the
  panel opens read-only, with Accept and Reject disabled. The ingress must route `/alignment` to the api.

## 0.1.8

- **Image placeholders show as images in the UI.** Synthesized `{{<deck>--<name>}}` placeholders resolve through
  `/source/resolve-image-urls` in the previews, the inspector and the editor. Stored markdown keeps the placeholder,
  which the export reads. This needs `api.sourceReader: store` (or `fixture`).
- **Dagster and the legacy ingestion code are removed from the api.** Ingestion runs in the platform's pipeline.
  Gone: `src/ingestion`, `src/semantic`, `src/pipelines` and the Dagster helpers, with `dagster*`,
  `unstructured[all-docs]`, `pdf2image`, `pillow`, `boto3`, `reportlab`, `python-docx`, `antlr4` and `openai` from the
  dependencies, and `libmagic1`, `libgl1` and `poppler-utils` from the image.
- **Renders always run in the api process.** `RENDER_RUNNER`, `DAGSTER_HOST` and `DAGSTER_PORT` are no longer read.
  The upgrade assumes nothing sets them: nothing does at work, by Chris's confirmation, and the sandbox already
  rendered locally. `/render/events/{run_id}` answers 404 for any id that isn't a local job.
