to: invincible-agent/seat/architect
from: training-consolidation-workbench/lane/wb
date: 2026-10-26
relay: Chris
This packet carries no secret and no infra detail.

# v0.1.0 released: readback

Chris merged PR #5 as master `aa97c11` and published release `v0.1.0` there. `release-chart.yml`
ran green in 34 s. Every value below was read back from ghcr anonymously, not from the run's log.

| what | value |
|---|---|
| chart | `oci://ghcr.io/edgy-solutions/training-consolidation-workbench/training-workbench:0.1.0`, `sha256:3a98a0de82ba06d935c34b70d229e05223750a359516f8c2010e324861b127e0`; version and appVersion are `0.1.0` |
| chart values | api `sha256:75008de0…1460c57`, ui `sha256:e79bf431…be3eea0` |
| `api:0.1.0`, `ui:0.1.0` | the same two digests |
| `image-digests.json` | both images built from `03335a8`, which is revision 19 on the sandbox |
| `:latest` | exists now on both images, from master's build of the merge (api `sha256:9f58bbc0…`, ui `sha256:10901045…`): the same code but different bytes, as expected |

The work packet's install line (`--version 0.1.0`) now resolves to the bytes that ran. lane/wb
continues as the working branch and merges to master by PR after each block.
