# Working in this repo

- **Session files are placed, never committed — by anyone, in any repo (ruled 2026-11-12).**
  Packets and handoffs are local files under `sessions/`, which is gitignored. Nobody commits
  or pushes a session file, and nobody force-adds one (`git add -f`). A sender drops its packet
  into the recipient's `sessions/` folder, and the recipient reads it there. Reports go in a
  packet, never in a PR.
- A branch that still tracks session files drops them when it next merges master: run
  `git rm -r -q --cached sessions` and commit that BEFORE the merge, so the merge doesn't
  delete the files from disk.
