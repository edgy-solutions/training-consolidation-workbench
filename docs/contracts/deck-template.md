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
roles:
  title:
    layout: title                # a layout name in the template
    placeholders: {title: 0, body: 1}
  section:
    layout: section
    placeholders: {title: 0}
  concept:
    layout: concept
    placeholders: {title: 0, body: 1, citation: 2, notes: notes-page}
  concept-with-figure:
    layout: concept-with-figure
    placeholders: {title: 0, body: 1, citation: 2, image: 3, notes: notes-page}
  summary:
    layout: summary
    placeholders: {title: 0, body: 1}
  sources:
    layout: sources
    placeholders: {title: 0, body: 1}
```

### 2.1 Roles

There are six roles, and each slide in the export has exactly one.

| Role | One slide per | Required fields | Optional fields |
|---|---|---|---|
| `title` | course (first slide) | `title` | `body` (subtitle) |
| `section` | section (§3.2) | `title` | `body` |
| `concept` | leaf without a figure | `title`, `body`, `citation` | `notes` |
| `concept-with-figure` | leaf with a figure | `title`, `body`, `citation`, `image` | `notes` |
| `summary` | course (after the last leaf) | `title`, `body` | |
| `sources` | course (last slide) | `title`, `body` | |

### 2.2 Fields

- **`title`, `body`, `citation`, `image`.** The value is the `idx` of a placeholder on the role's layout. `image` must name a placeholder that accepts a picture (picture or object type).
- **`notes`.** The value is `notes-page` (the slide's speaker-notes page) or a placeholder `idx`. If it is omitted, it means `notes-page`. The notes page exists in every deck, so the default cannot drop content.

### 2.3 Validation

The exporter checks the mapping against the template and the course **before writing any slide**. It collects every failure and raises them together, each naming the role, field, layout or placeholder involved. Each of these is a failure:

- `deck_template` is missing or is not `1`, or the template file is missing.
- **A role the course needs is not mapped.** The message names the role (`role 'concept-with-figure' is not mapped`). Roles the course does not need may be left unmapped.
- An unknown role or field name. Typos fail; they are not ignored.
- A `layout` that no slide layout in the template carries, or that more than one layout carries. The message lists the template's layout names.
- A placeholder `idx` the layout does not have, or an `image` placeholder that cannot take a picture.
- A required field (§2.1) that is not mapped.
- **Content with no mapped field to go to,** for example a title slide with a subtitle when the `title` role maps no `body`. Content is never dropped.

**Nothing falls back.** There is no default role, default layout or "first layout". An export either meets this contract or fails.

### 2.4 What the exporter does with the template

- Slides already in the template are dropped. Only its masters and layouts are used.
- A placeholder on a layout that the mapping does not fill is removed from the slide, so no empty prompt boxes remain.
- Text goes into the placeholder's text frame and inherits the layout's styling. The exporter sets no font, size or colour, except that `**bold**` runs are bold.
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
| a TargetNode with children | a `section` slide (`title` only; nesting deeper than one level still gives a `section` slide per node) |
| a TargetNode without children (a leaf) | a `concept-with-figure` slide if it has a figure (§3.4), otherwise a `concept` slide |

### 3.3 A leaf's fields

- **`title`** is the node's title.
- **`concepts`** are the node's `key_concepts`. If it has none, they are the concepts its source slides `TEACHES`, in descending salience. A leaf with no concepts fails.
- **`body`** is `content_markdown` with the image markup removed. An empty body (whitespace only) fails: it would be a blank slide.
- **`sources`** are the slides the node is `DERIVED_FROM`. Each one gives a deck `filename` and a slide `number` (source contract §4.1). A leaf with no sources fails. A source slide the reader cannot find also fails.
- **`notes`** hold the node's speaker notes, if there are any, and always end with the line `Concepts: <name>; <name>`.

**Each concept appears exactly once.** A concept named by two leaves fails, and the message names both leaves. In a consolidated course, a concept taught twice means the consolidation is not finished.

### 3.4 Figures

- **What a figure is.** A leaf's figure is the first image reference in its `content_markdown`, either `![alt](ref)` or the synthesizer's `{{asset_id}}`. A leaf with more than one image reference fails, because a role holds one image.
- **How a reference is resolved.** The resolver turns a reference into bytes. It accepts:
  - a source-contract image key (`…/images/slide_{n}_img_{k}.png`);
  - a fixture reference (`fixture://images/<name>`, `/source/fixture-asset/<name>`);
  - a presigned URL, read by its key with the query dropped;
  - an `asset_id` the reader can map to a key.
- **An unresolvable reference fails.** An image is never dropped silently.

### 3.5 Generated slides

- **`summary`.** `title` "Summary"; `body` lists every concept once, one bullet each, in course order.
- **`sources`.** `title` "Sources"; `body` has one line per source deck, in order of first citation: `<filename>: slides 1, 2, 4`.

## 4. Citations

Every concept slide's `citation` field reads:

- `Source: <filename>, slide <n>` for one slide;
- `Sources: <filename>, slides <n>, <m>; <filename>, slide <k>` for several.

Decks appear in order of first citation, and slide numbers ascend within a deck. `<n>` is the source slide's `number`, its position in the deck, counting hidden slides (source contract §4.1).

## 5. Failures

The exporter raises one error listing every problem it found, in the order above:
- mapping problems (§2.3);
- course problems (§3.3, §3.4);
- unresolvable images (§3.4);
- round-trip problems (§6).

**No file is written when anything fails.**

## 6. Round-trip check

The check reads the written `.pptx` back and compares it with the course. It runs inside every export, and the golden test runs it too. It asserts:

1. **Slide sequence.** The course gives an expected role sequence: title, then sections and leaves in tree order, then summary, then sources. The mapping turns that into expected layout names. The deck's slide count and each slide's layout name must equal them. Two roles may share a layout, so a role is never recovered from a layout name alone.
2. **Every concept once.** Every concept in the course appears on exactly one concept slide, in its `Concepts:` notes line.
3. **Citations.** Every concept slide's citation text equals §4's rendering of that leaf's sources.
4. **Images.** Every `concept-with-figure` slide holds a picture, and no other slide does.
5. **Nothing extra.**
   - No concept, citation, deck or slide appears in the export that is not in the course.
   - The summary lists exactly the course's concepts.
   - The sources slide lists exactly the cited decks and slides.

## 7. Changing this contract

- **Adding a role or field** is a contract change: bump `deck_template` and update the stand-in and its mapping in the same commit.
- **A new template** (the customer's included) is a data change: one `.pptx` plus one mapping file, kept wherever that template's owner keeps them.
