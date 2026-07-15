---
status: accepted
---

# A landing-page ground-truth URL is Unscoreable, not Hit or Unknown

When the ground-truth license-code-url downloads as HTML (a landing page, not
a file) while the inferred URL downloads fine, `compare_url_content` returns
the deterministic `UNSCOREABLE` sentinel on `EqResult.verdict` — decided from
the fetch's Content-Type at download time (`DownloadResult.fail_kind ==
"html"`), never a host allowlist. It only fires when the agent's own file
downloaded OK: an HTML ground truth paired with a failed inferred download is
still an ordinary `FALSE`. `grade_item` maps it to the fourth grade
**Unscoreable**, which any Hit-rate calculation must exclude from its
denominator — the field genuinely can't be graded either way. The judge is
untouched: it never issues `UNSCOREABLE`, only `TRUE`/`FALSE`.

**Rejected:**

- A host allowlist for known landing-page domains — rots as new hosts appear
  and misses landing pages on hosts that also serve real files.
- Grading it **Hit** — inflates the headline number for a case where nothing
  was actually verified.
- Grading it **Unknown** — implies the agent failed to answer, when the agent
  found a real, downloadable file; the ground truth is what's unusable.
