---
status: accepted
---

# A stray upstream holder is rejected only outside its own package family

`_is_stray_holder` guards against copyright text that names a generic
upstream holder ("The Go Authors", the Android Open Source Project) instead
of the package actually being resolved. A holder-only denylist can't tell a
legitimate Go/Android component from a misattributed one — it rejected "The
Go Authors" even for a real `pkg:golang/` package, and AOSP even for a real
Android package. Each rule now pairs the holder phrase with a family
predicate (`purl`/`lib_name`) — "the go authors" is stray unless the purl is
`pkg:golang/...`; AOSP is stray unless `android` appears in the purl or
`lib_name`. The holder is rejected only when its phrase matches AND the
package is NOT of that family. The guard stays reject-only: a matching family
predicate makes the holder legitimate, never promotes a result — this never
turns a Mismatch into a Hit, only avoids a false stray-holder rejection.

**Rejected:**

- Holder-only denylist (the bug) — rejects legitimate Go/Android packages
  that genuinely carry their own upstream holder's notice.
- Remove the guard entirely — reopens the misattribution the tranche added it
  to close, for every package that isn't Go or Android.
