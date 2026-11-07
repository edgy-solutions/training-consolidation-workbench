# Contract: deck template → workbench exporter

**Version:** `deck_template: 1`

**What this contract does.** The workbench exports a consolidated course as a `.pptx` deck. Everything specific to one template lives in two files: the template `.pptx` and a mapping file. The exporter's code names no template, no layout and no placeholder index. Adopting a new template therefore means adding one mapping file and one `.pptx`, with no code change.

**Where templates live.**
- The repo holds one template: the stand-in at [`tests/fixtures/templates/standin/`](../../tests/fixtures/templates/standin/). It is a test fixture: plain, with one layout per role. The default export uses it.
- A customer's template, its name and its styling vocabulary never enter this repo. They are committed where the customer's work is kept.

## 1. Inputs

The exporter takes three things:
1. **A consolidated course** (§3).
2. **A mapping file**, `deck-template.yaml` (§2). It names its template `.pptx` by a path relative to itself.
3. **An image resolver**, which turns an image reference from the course into bytes (§3.4).

Its output is one `.pptx`. Before returning, it runs the round-trip check (§6) on that file and fails if the check finds anything.

## 2. The mapping file

```yaml
deck_template: 1                 # this contract's version
template: standin.pptx           # path relative to this file
max_bullets_per_slide: 5         # optional; a longer body continues on the next slide
max_summary_items: 12            # optional; concepts beyond this go in the summary's notes
roles:
  title:
    layout: title                # a layout name in the template
    placeholders: {title: 0, body: 1}
  section:
    layout: section
    placeholders: {title: 0, body: 1}
  concept:
    layout: concept
    placeholders: {title: 0, body: 1, notes: notes-page}
  concept-with-figure:
    layout: concept-with-figure
    placeholders: {title: 0, body: 1, image: 3, notes: notes-page}
  summary:
    layout: summary
    placeholders: {title: 0, body: 1}
  sources:
    layout: sources
    placeholders: {title: 0, body: 1}
```

A role may also carry `layout_index`, which is optional. It is the 0-based position of the layout among all the layouts in the template, counting each slide master in turn and then that master's layouts in order. It must agree with `layout`: the layout at that position must have that name. It is how a role picks one layout when several carry the same name (§2.3).

```yaml
  concept:
    layout: Title Only
    layout_index: 7
    placeholders: {title: 0, body: 1}
```

### 2.1 Roles

There are six roles, and each slide in the export has exactly one.

| Role | One slide per | Required fields | Optional fields |
|---|---|---|---|
| `title` | course (first slide) | `title` | `body` (subtitle) |
| `section` | section with a body, plus continuations (§3.2, §2.4) | `title` | `body` |
| `concept` | leaf without a figure, and each continuation (§2.4) | `title`, `body` | `notes` |
| `concept-with-figure` | leaf with a figure (its first slide) | `title`, `body`, `image` | `notes` |
| `summary` | course (after the last leaf), plus continuations (§2.4) | `title`, `body` | |
| `sources` | course (last slide) | `title`, `body` | |

### 2.2 Fields

- **`title`, `body`, `image`.** The value is the `idx` of a placeholder on the role's layout. `image` must name a placeholder that accepts a picture (picture or object type).
- **`notes`.** The value is `notes-page` (the slide's speaker-notes page) or a placeholder `idx`. If it is omitted, it means `notes-page`. The notes page exists in every deck, so the default cannot drop content. The citation (§4) goes here. Notes carry the citation, so a course with sources cannot use a placeholder here: the round trip refuses a filename on a slide face (§6).
- **`citation` is retired.** A mapping that still names `citation` on `concept` or `concept-with-figure` is accepted: the exporter warns (`role 'concept': field 'citation' is retired; citations now go in the speaker notes and the placeholder is removed from the slide`), does not check its `idx`, writes nothing to it, and removes that placeholder from the slide. The `sources` role has no `notes` field to map: its notes page is always written (§3.5).
- **`max_bullets_per_slide`.** A top-level setting, optional, default `5`: a whole number of at least 1. It is how many lines a body may hold before it continues on another slide (§2.4).
- **`max_summary_items`.** A top-level setting, optional, default `12`: a whole number of at least 1. It is how many concepts the summary slides list; the rest go in the last summary slide's speaker notes (§3.5).

### 2.3 Validation

The exporter checks the mapping against the template and the course **before writing any slide**. It collects every failure and raises them together, each naming the role, field, layout or placeholder involved. Each of these is a failure:

- `deck_template` is missing or is not `1`, or the template file is missing.
- **A role the course needs is not mapped.** The message names the role (`role 'concept-with-figure' is not mapped`). Roles the course does not need may be left unmapped.
- An unknown role or field name. Typos fail; they are not ignored. The retired `citation` (§2.2) is the one exception.
- A `max_bullets_per_slide` that is not a whole number of at least 1 (`max_bullets_per_slide must be a whole number of at least 1, got '5'`). A boolean is not a number here.
- A `max_summary_items` that is not a whole number of at least 1 (`max_summary_items must be a whole number of at least 1, got 0`). A boolean is not a number here.
- A `layout` that no slide layout in the template carries. The message lists the template's layout names.
- A `layout_index` that is out of range, is not an integer, or is the position of a layout with a different name from `layout`. The message names the role, the index and both names.
- A placeholder `idx` the layout does not have (checked against the layout the role resolves to), or an `image` placeholder that cannot take a picture.
- A required field (§2.1) that is not mapped.
- **Content with no mapped field to go to,** for example a title slide with a subtitle when the `title` role maps no `body`. Content is never dropped. The one exception is a section body: when the `section` role maps no `body`, section slides are skipped and recorded (§3.2), and the exporter warns.
- **Headings.** A heading line equal to the slide's title (case and spacing ignored) is removed as a duplicate, when other lines remain; any other heading stays. The first remaining heading on a slide is its bold subtitle (level 0, no bullet). Any further heading renders as a plain level-0 line with no bullet, so a slide never has two bold heading lines.

**Nothing falls back,** with one exception. There is no default role or default layout. The exception is a name that several layouts carry, with no `layout_index`: the exporter uses the first of them in template order and warns. A `layout_index` that agrees with `layout` always chooses that layout. Everything else either meets this contract or fails.

**A duplicate layout name is a warning, never a failure.** Corporate templates often reuse a name. The warning names the role, the layout name, how many layouts carry it and the position used; for the no-index case it also says to set `layout_index`. It is printed once per export, and the settings screen shows it when the template is opened and after a save (`warnings` in the settings state). A save is never refused for it. A layout name carried by one layout needs no `layout_index` and gives no warning.

### 2.4 What the exporter does with the template

- Slides already in the template are dropped. Only its masters and layouts are used.
- A placeholder on a layout that the mapping does not fill is removed from the slide, so no empty prompt boxes remain.
- Text goes into the placeholder's text frame and inherits the layout's styling. The exporter sets no font, size or colour, except that `**bold**` runs are bold.
- A `body` placeholder is set to shrink text on overflow (`normAutofit`); the viewer applies the shrink. The exporter still sets no font, size or colour.
- **One slide per leaf, plus continuations.** A body with more than `max_bullets_per_slide` lines continues on further slides.
  - Every non-blank line counts 1, whether bullet, paragraph or nested bullet, except a heading (`#`), which counts 0.
  - A block stays together: a bullet with its indented lines. A heading stays with the block that follows it; a heading at the end stays with the block before it.
  - Blocks fill a slide in order. A block that alone is over the limit is cut by line at the limit.
  - A body within the limit is written unchanged.
  - A continuation's title is the leaf's title plus ` (cont.)`, and its role is `concept`, even for a figure leaf, so a figure leaf's course needs the `concept` role mapped. The figure goes on the first slide only, and the leaf's own notes go on the first slide only. Every part carries the citation and `Concepts:` line (§3.3).
  - A section body splits the same way. Its continuations are titled the section's title plus ` (cont.)` and keep the role `section`.
  - The summary's shown concepts, one bullet each, are spread evenly over the fewest slides that hold them at `max_bullets_per_slide` each, the earlier slides taking one more when they don't divide evenly (12 at 5 → 4, 4, 4; 11 → 4, 4, 3): `Summary`, then `Summary (cont.)`. There is always at least one.
- The image is placed into its placeholder, which crops it to fit (`insert_picture`).

## 3. The consolidated course

The exporter's input is built from the project tree that the draft routes keep (`Project -HAS_CHILD-> TargetNode …`) and the source slides that tree points at.

### 3.1 Order

The order is the tree, depth-first. Siblings are sorted by `order` ascending; a node with no `order` sorts after its ordered siblings, in creation order (`id` as the tiebreak). A section's slide comes immediately before its descendants' slides.

### 3.2 What each node becomes

| Node | Becomes |
|---|---|
| the Project | the `title` slide. `title` is the project title; `body` is "Consolidated from N source decks" ("1 source deck" when there is one). |
| a TargetNode with `is_unassigned`, and its subtree | nothing: "Unassigned / For Review" is not part of the course |
| a TargetNode with children | a `section` slide whose `title` is the node's title and whose `body` is the node's `content_markdown`, split like a leaf body (§2.4); nesting deeper than one level still gives a `section` slide per node. When the node has no body, or the mapping maps no `section` `body`, there is no slide, and the section is listed under `skipped_sections` in the render record (§3.3). Its children still get their slides. |
| a TargetNode without children (a leaf) | a `concept-with-figure` slide if it has a figure (§3.4), otherwise a `concept` slide |

### 3.3 A leaf's fields

- **`title`** is the node's title.
- **`concepts`** are the node's `key_concepts`. If it has none, they are the concepts its source slides `TEACHES`, in descending salience. A leaf with no concepts fails.
- **`body`** is `content_markdown` with the image markup removed. An empty body (whitespace only) fails: it would be a blank slide.
- **`sources`** are the node's recorded source slides (`source_slide_ids`), resolved through the decks the course records (`source_deck_ids` on the Project), not through whatever the graph holds. Each one gives a deck `filename` and a slide `number` (source contract §4.1). Three failures, all listed with the others: the course records no source decks; a recorded deck is not found; a source slide is not in any recorded deck (`leaf '<title>': source slide '<id>' is not in any deck this course was built from`). A leaf with no sources fails.
- **`notes`** are, in order: the node's speaker notes if there are any; the citation line (§4); and the line `Concepts: <name>; <name>`, which is always last.

**A concept may be taught on more than one leaf.** A repeat is not a failure.
- A leaf's *role* is the `section_type` of its top-level ancestor (`introduction`, `mandatory_safety`, `technical`, `mandatory_assessment`; missing means `technical`), inherited down the tree.
- A repeat that involves an `introduction`, `mandatory_safety` or `mandatory_assessment` leaf is by design and passes silently. Every other role, unknown values included, is a concept role.
- A concept named by two or more concept-role leaves is an **overlap**. It is judged per concept: if it is on an introduction leaf and on concept-role leaves A and B, the overlap is A and B. Only leaves count; a concept on a parent section does not.
- Rendering a course with an overlap needs an explicit "render anyway" with a reason. The render route answers 409 until it has one, and `render_project` refuses on its own, so a background job or a race cannot skip it.
- The reason is recorded, not delivered: `render_overrides` on the Project holds one JSON entry per such render (`schema`, `slides_sha256`, `reason`, `by`, `at`, `filename`, `overlaps`, `skipped_sections`), joined to the deck by `slides_sha256` (§6). The entry is also written when sections are skipped (§3.2): `skipped_sections` lists each as `{id, title}`, and `reason`, `by` and `at` are null when nothing was overridden. The deck itself carries no free text; its properties say only `render_anyway=yes`.

**Gate order.** A pptx render stops at the first of these: (1) unfinished sections (a leaf with no source slides or an empty body), reported as "N of M sections unfinished" before any concept check; (2) build problems (§5); (3) overlaps. A reason overrides only the third.

### 3.4 Figures

- **What a figure is.** A leaf's figure is the first image reference in its `content_markdown`, either `![alt](ref)` or the synthesizer's `{{asset_id}}`. A leaf with more than one image reference fails, because a role holds one image.
- **How a reference is resolved.** The resolver turns a reference into bytes. It accepts:
  - a source-contract image key (`…/images/slide_{n}_img_{k}.png`);
  - a fixture reference (`fixture://images/<id>`, `/source/fixture-asset/<id>`);
  - a presigned URL, read by its key with the query dropped;
  - an image id (`{{id}}`) the reader can map to a key.
- **Image ids are `<deck>--<name>`.** `<deck>` is the first 12 characters of the deck's course id after its `sha256:` prefix (lowercase hex), `<name>` the image file name. The synthesizer always emits the prefixed id. An id without the prefix is refused (`image '<id>' carries no deck prefix; image ids are '<deck>--<name>'`), and so is a prefix that names a deck the course does not record (`… names deck prefix '<p>', which is not a deck this course was built from`).
- **An unresolvable reference fails.** An image is never dropped silently.

### 3.5 Generated slides

- **`summary`.** `title` "Summary"; `body` lists the first `max_summary_items` concepts, one bullet each, in course order. It continues like any body (§2.4). When concepts remain, the last summary slide's body ends with one more line, `+<n> more in notes` (`+1 more in notes` for one), written as a plain line with no bullet marker and not counted against `max_bullets_per_slide`, so it never makes a slide of its own. It renders at level 0 with no bullet and not bold, whatever the placeholder gives its paragraphs. The remaining concepts are in that slide's speaker notes, one per line in course order. At or under the cap the summary has no such line and no notes.
- **`sources`.** `title` "Sources"; `body` is a count line, `<n> source decks, <m> cited slides` ("1 source deck", "1 cited slide" in the singular). The slide's speaker notes have one line per source deck, in order of first citation: `<filename>: slides 1, 2, 4`.

## 4. Citations

Every concept slide's speaker notes carry a citation line, directly before the `Concepts:` line. It reads:

- `Source: <filename>, slide <n>` for one slide;
- `Sources: <filename>, slides <n>, <m>; <filename>, slide <k>` for several.

Decks appear in order of first citation, and slide numbers ascend within a deck. `<n>` is the source slide's `number`, its position in the deck, counting hidden slides (source contract §4.1).

**No source filename reaches a slide face.** A filename appears only in speaker notes.

## 5. Failures

The exporter raises one error listing every problem it found, in the order above:
- mapping problems (§2.3);
- course problems (§3.3, §3.4);
- unresolvable images (§3.4);
- round-trip problems (§6).

**No file is written when anything fails.**

## 6. Round-trip check

The check reads the written `.pptx` back and compares it with the course. It runs inside every export, and the golden test runs it too. It asserts:

1. **Slide sequence.** The course gives an expected role sequence: title, then sections that get a slide (§3.2) and leaves in tree order (a slide's continuations after it, §2.4), then summary (with its continuations), then sources. The mapping turns that into expected layout names. The deck's slide count and each slide's layout name must equal them. Two roles may share a layout, so a role is never recovered from a layout name alone.
2. **Every concept on its leaves.** Each leaf's `Concepts:` notes line equals that leaf's concepts, and every concept in the course appears on at least one concept slide.
3. **Citations.** Every concept slide's notes hold §4's rendering of that leaf's sources, directly before the `Concepts:` line.
4. **Images.** Every `concept-with-figure` slide holds a picture, and no other slide does.
5. **Nothing extra.**
   - No concept, citation, deck or slide appears in the export that is not in the course.
   - The summary slides' faces, with the last one's speaker notes, together list exactly the course's concepts: the faces the first `max_summary_items` and the `+<n> more in notes` line, the notes the rest.
   - The sources slide's face is the count line (§3.5) and its notes list exactly the cited decks and slides.
   - No source filename is on any slide face (§4).
6. **The deck records its content.** The deck's `comments` property reads `deck_export/1 slides_sha256=<hex>`, with ` render_anyway=yes` appended when the render went ahead over an overlap. The digest is the sha256 of the canonical JSON of each slide's number, role, expected fields and picture bytes, so two exports of one course give one digest. The exporter reads the property back after saving.

## 7. Changing this contract

- **Adding a role or field** is a contract change: bump `deck_template` and update the stand-in and its mapping in the same commit.
- **Adding an optional key with a default** does not bump `deck_template`: a mapping written before it still validates and means what it meant. `layout_index`, `max_bullets_per_slide` and `max_summary_items` are such keys.
- **A new template** (the customer's included) is a data change: one `.pptx` plus one mapping file, kept wherever that template's owner keeps them.

## 8. Choosing the template from the settings screen

A person holding `can_configure:deck_template` (Topaz) can upload a template and map its roles in the workbench's settings screen, instead of shipping a mapping file with the deployment. The mapping format (§2) and its validation (§2.3) are unchanged, and `deck_template` stays `1`.

**Which template is in force.** In this order:
1. the template saved from the screen;
2. the deployment's `DECK_TEMPLATE_URI` and `DECK_TEMPLATE` (§1);
3. the repo stand-in.

Nothing falls back past a failure: if the store holds a pointer but cannot be read, exports fail naming the store, and they do not use a lower choice. Saving from the screen is on only when `DECK_TEMPLATE_STORE=s3://<bucket>/<prefix>` is set. Unset, the store is never read and the order is just 2 then 3.

**The flag.** The screen is behind `WB_DECK_TEMPLATE_UI` (chart `api.deckTemplate.ui`), default off, in addition to `can_configure:deck_template`. Off: the gear is not shown and every `/settings/deck-template` route except `/settings/deck-template/enabled` answers 404. Exports do not read the flag: a saved template stays in force, so turning the flag off does not change decks. Going back to the deployment's template means Reset before turning it off, or deleting `active.yaml`.

**Routing.** The screen's routes live under `/settings`. Where the UI and the api share one host, the api's ingress lists its route prefixes (chart `api.ingress.paths`), and that list must include `/settings` (and `/alignment`, for proposal review). A prefix left out is answered by the UI with its `index.html`, so the gear's question gets no `enabled` and the gear never shows, with the flag on and the grant in place. A deployment that gives the api its own host with the path `/` needs nothing. Each deployment's values carry this list, so check them when turning the flag on.

**Store layout.**
- `<prefix>/<sha256>.pptx`: the template, named by the hash of its bytes. The uploaded file name is never part of a key.
- `<prefix>/active.yaml`: the one pointer. It holds `deck_template: 1`, `template: s3://…/<sha256>.pptx`, `source: {filename, saved_by, saved_at}` and `roles` (§2). The `.pptx` is written first and the pointer last, so a save either lands whole or not at all.
- "Reset to deployment default" deletes `active.yaml` only. The `.pptx` objects stay.

**What a save must meet.** All six roles must be mapped, which is stricter than §2.3's per-course rule, so a saved template can never later fail with "role not mapped". A field cannot be mapped to a date, footer or slide-number placeholder: python-pptx does not copy those onto a new slide, so they could never be filled. A duplicate layout name is a warning, not a refusal (§2.3). Every problem is reported together.

**The trial export.** After the checks above, the workbench runs the real exporter, round-trip check included (§6), on a small built-in course with a section, a concept slide, a figure slide, a summary and a sources slide. If that fails, nothing is written to the store.
