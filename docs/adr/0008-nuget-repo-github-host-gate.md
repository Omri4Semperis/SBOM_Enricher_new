---
status: accepted
---

# A NuGet raw-URL is only derived from a recognized GitHub host

`nuget_candidates` builds `raw.githubusercontent.com` LICENSE URLs from a
nuspec's `<repository url>` by reducing it to `owner/repo`. That reduction is
only trustworthy when the URL's host is a recognized GitHub host
(`github.com`/`www.github.com` — the same set `rewrite_viewer_to_raw` uses).
When the host is anything else (GitLab, a private mirror, a placeholder
domain), the function now returns `[]` instead of emitting a raw URL —
because collapsing an arbitrary host's `owner/repo` onto GitHub can silently
attribute an unrelated GitHub repository's license to the package being
enriched. Fail-closed here matches the function's existing contract: no
usable, verified source means no candidate, never a guess.

**Rejected:**

- Implement each other host's real raw-URL form (GitLab's `-/raw/`, etc.) —
  rots as new hosts appear, and each added host is a new opportunity for the
  same owner/repo collision, just moved one host over.
- Trust the `owner/repo` regardless of host — the bug this ADR closes.
