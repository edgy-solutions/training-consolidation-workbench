to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-26
relay: Chris
This packet carries no secret and no infra detail.

# PR #5 open; the chart releases by version

1. **PR lane/wb → master: #5, open for Chris to merge.** master is an ancestor of lane/wb, so
   it merges clean. From the merge on, work installs from master's releases, and lane/wb merges
   back by PR after each block.
2. **Versioned chart (b118cbf).** `release-chart.yml` runs on `release: published` and nothing
   is built on a tag. It refuses four things: a tag other than `v<Chart.yaml version>`, an
   `appVersion` that differs from the version, a commit not on master, and a version already
   on ghcr. Then it:
   - tags `api:<version>` and `ui:<version>` by digest;
   - bakes both digests into the packaged chart's values;
   - pushes the chart to `oci://ghcr.io/edgy-solutions/training-consolidation-workbench/training-workbench`;
   - attaches `image-digests.json` and the `.tgz` to the release.

   **Which digests it ships.** CI finds them; nobody types them in. They come from one commit:
   the oldest ancestor whose api and ui build contexts both equal the release commit's, with
   both images published. The builds are not reproducible. The merge commit gets rebuilt with
   new digests, and so would the same code at any other commit. This rule ships the pair a lane
   rolled and tested, not a rebuild. For the merge it resolves to 03335a8: api
   `sha256:75008de0…`, ui `sha256:e79bf431…`, revision 19's bytes. I checked that against
   ghcr from the lane's head.

   Picking each image on its own was wrong, and the first run showed it. It would have shipped
   ui from f08d0c3: the same frontend code, but a build that never ran.

   The `.dockerignore` files now leave out files the images never run (`*.md`, `roll.sh`, and
   the ignore files), so editing them does not make the tested build look stale.
   `build-container.yml` (the old `course-tools` image, which nothing pulls) loses its `v*` tag
   trigger.
3. **roll.sh header:** it says it is a lane roll from the working tree for the sandbox, and that
   work installs a released chart by version.

**Work packet:** section 1 now installs `training-workbench --version 0.1.0` from ghcr. Its
values name no image, and its check reads `helm list` and the pods' imageIDs.

**Next, after Chris merges #5:** publish GitHub release `v0.1.0` on master, the one manual act,
which the architect asked for. Then I read back the chart digest and the two image digests
from the run's summary. The merge's push to master also creates `:latest` on both images. It
has never existed, because master had no push since `build-images.yml` landed. It points at
master's own build, not at the release's digests.
