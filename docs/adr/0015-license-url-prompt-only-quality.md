---
status: accepted
---

# License-URL quality is enforced by prompt only (no new detection)

The license-inference prompt demands a URL to the component's **own** published
license/copyright file (repo or package platform) that names a concrete holder
for that component — the meaning of Inferred License Code URL in `CONTEXT.md`.
Canonical/boilerplate license text (e.g. full LGPLv3 legalese naming no holder)
is forbidden; when LICENSE/COPYING is boilerplate, prefer AUTHORS/NOTICE/COPYRIGHT
(worked negative example: nettle `.lesserv3` → `AUTHORS`). No new detection or
validation code; deliberately not a hard "must be a repo" rule.

**Rejected:** post-download detection of boilerplate / holder absence — would
add a new code path for a quality issue that is rare enough to try prompt-first.
Hard "must be a repo URL" — too strict for valid package-platform files.
