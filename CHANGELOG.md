# Changelog

Chart releases, newest first. A release is the GitHub release `v<version>`; earlier ones are described there.

## Unreleased

- **Alignment review UI, behind `api.alignmentReviewUi`** (renders `WB_ALIGNMENT_REVIEW_UI=on`; default off). A Review
  entry in the top bar opens a per-course list of open alignment proposals with Accept and Reject. The entry shows
  only when the flag is on and Topaz grants the user `can_review:<alignmentReviewSubject>`. The new
  `GET /alignment/review-access` answers `{enabled, can_review}`. With the flag off it asks nothing of the decider;
  if the decider is unavailable it answers 503. Deciding still needs `WB_STORE_WRITES=on`, and the ingress must route
  `/alignment` to the api.

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
