---
status: accepted
---

# URL equality is LICENSE content sameness, not string equality

`is_eq_license_code_url` is TRUE only when the inferred URL and the ground-truth
URL both download successfully and resolve to the same LICENSE text (byte
identity → whitespace/BOM/line-ending/case normalize → GPT-4.1 judge). A failed
ground-truth or inferred download is FALSE (reason in `results_extended.csv`),
never an ambiguous miss.

**Rejected:** comparing URL strings (or normalized URL strings) — two different
hosts often serve the same file, and identical-looking URLs can diverge after
redirects.
