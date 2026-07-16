# Perf analysis — run `20260716_102127_ClaudeOpu-4-8_380`

Analysis only. No `src/` edits, no fixes applied. Evidence = mid-run copy
(`… - Copy`, 221 fully-written CSV rows of 380; torn rows discarded). Scripts:
`ad_hoc_scripts/analysis/{parse_run_latency,concurrency_timeline}.py`.

Run config (snapshot): model `claude-opus-4-8`, workers 30, `cache_read=null`
(cold, 0 hits), audit ON (GT_380 has all 3 gt columns).

> **Update 2026-07-16 (post-review):** the original "single fix = re-add a
> 300s Claude timeout" was **wrong** — see the Correction section. Slow Claude
> calls are productive/correct, not hung; a 300s cap would destroy correct
> results. The real leading pathology is the **GPT-4.1 copyright-extract call
> (~109s median)**, plausibly from the per-call `Gpt41Client()`. Sections (b)/(c)
> below are revised; the latency table (a) is unchanged.
>
> **Implementation 2026-07-16:** the confirmed minimal fix is now applied:
> `run_workers` constructs one `Gpt41Client` per run and shares it with both
> copyright extraction and audit equality. The 60s GPT timeout, retry policy,
> and concurrency model are intentionally unchanged. A new live run is needed
> to measure the impact and confirm that the freeze no longer occurs.

## TL;DR

Most of the wall is **inherent**: two sequential Claude Opus calls per component
(license mean 199s + copyright web-fallback mean 175s, fires ~45%), same ladder
and model as old_code, and the semaphore **does reach 30**. But there is a
second, **pathological** cost I initially buried: the GPT-4.1 **copyright
extract** step runs a **109s median** on the file-only path — impossible for a
healthy call (client `timeout=60, max_retries=0` ⇒ any single success ≤60s), so
it is **timing out and retrying / starving**. It runs on nearly every component.
Prime suspect: `copyright.py` builds a fresh `Gpt41Client()` (blocking
`DefaultAzureCredential`, no pooling/token-cache) **per call** — a regression
from old_code, which builds one shared client.

## (a) Per-stage latency (real numbers, n=221 finished, seconds)

| Stage | calls | sum | mean | median | p90 | max |
|---|---|---|---|---|---|---|
| license inference (Claude Opus) | 221 | 43,898 | 198.6 | 182.4 | 288.0 | 420.9 |
| copyright resolve (GPT extract [+Claude web]) | 220 | 38,428 | 174.7 | 143.5 | 314.2 | 536.3 |
| download + equality + overhead (residual) | 220 | 5,093 | 23.2 | 12.5 | 30.8 | 732.0 |
| **total / component** | 221 | 87,442 | **395.7** | **383.7** | 589.1 | 1166.3 |

- license retries: **0** (all `attempts=1`).
- copyright path: **web (2nd Opus call) 99/221 (45%)**, npm 18, file/UNKNOWN rest.
- Claude calls **>300s**: license 17 (8%), copyright 26 (12%) — unbounded, but
  **productive** (see Correction), not hung.
- **GPT-4.1 copyright extract** (inside the copyright column) = **109s median on
  the file-only path** — the buried pathology (see Correction/(c)).
- residual mean 23s bounds non-Claude *equality/download* work; one 732s
  outlier = a stuck download chain in URL-content equality.

### Reconciling "600s"
User figure = `4740s × 30 / 233 ≈ 610` **worker-seconds**/component. Measured
compute of *finished* comps = 396s. Gap ≈ 214s is **not idle workers**: it's
(1) heavy right tail (max 1166s, no Claude timeout) hogging slots, and
(2) survivorship bias — slow components still in-flight occupy the 30 slots but
aren't in the completed count. Sweep-line over preserved mtimes: **peak
concurrency = 30**, avg = 20.4. avg<peak is *partly* ramp + survivorship, but
(see Correction) **partly real event-loop starvation** from blocking per-call
AAD credential construction.

## (b) Ranked hypotheses (cheapest-to-check first)

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| 1 | 429 / rate-limit retries & backoff | **REFUTED** | 0 license retries (attempts=1); backoff is only 2–8s; GPT `max_retries=0`. No 429 in stories. |
| 2 | Effective concurrency < 30 (semaphore/await/sync-in-async) | **PARTLY CONFIRMED** | Semaphore ceiling reaches 30 (not misconfigured), but a **sync-in-async** path exists: `Gpt41Client()` per copyright call builds a blocking `DefaultAzureCredential`; token fetch on the loop thread stalls all workers. avg concurrency 20.4 < peak 30. |
| 3 | Serialization point (cache/writer/lock) | **CONFIRMED (client, not writer)** | Writer/cache are fine. But **fresh `Gpt41Client()` per copyright extract** → GPT file-only path 109s median, >60s single-call ceiling ⇒ retries/starvation. Blocking AAD credential is a serialization point. **Leading pathology.** |
| 4 | More LLM round-trips / slow Claude calls | **CONFIRMED but INHERENT** | 2 sequential Opus+WebSearch calls (199s+175s) dominate. Same file→npm→web ladder as old_code → **not** more calls; it's model latency, not a code bug. |
| 5 | Removed per-Claude-call timeout | **REFUTED as a fix** | old_code capped Claude at 300s; new has none. But finished data: license calls >300s → 17/17 produced a value, 11 correct; >360s → 4/4 correct. A 300s cap **destroys correct results**. Only a high safety-net (~900–1200s) for true hangs is defensible. |

### Normalization vs `knowledge/old_code/` (separating inherent from bug)
| Axis | old_code | this run | effect |
|---|---|---|---|
| model | claude-opus-4-8 | claude-opus-4-8 | same |
| workers | default 20 (max 30) | 30 | new has *more* license concurrency |
| concurrency model | **fine-grained pools**: infer(20), judge(8), fetch(10), copyright-infer(8) — sem held only around each call | **single sem(30)** around whole component | new holds a slot through downloads/GPT judges (~6% duty-cycle loss) |
| gt columns | all 3 (audit on) | all 3 (audit on) | comparable |
| equality work | license-name + copyright judges + a consistency judge | name + copyright judges **+ URL-content equality (2 extra downloads + big GPT judge)**, no consistency judge | new adds per-component download+judge work (small, in residual) |
| copyright ladder | file → npm → Claude web | file → npm → Claude web | **identical call count** |
| Claude per-call timeout | **300s, fail-closed** | **none** | new tail unbounded → slot hogging |

Conclusion: new code does **not** issue more LLM calls per component than
old_code. The two Opus calls (~400s) are inherent. On top of that sits a
**GPT-4.1 pathology**: the copyright-extract call, run on nearly every
component, takes ~109s median where a healthy call is ≤60s — a real bug, not
model latency.

## Correction (supersedes the original single-fix claim)

Two evidence checks (`ad_hoc_scripts/analysis/timeout_and_gptclient.py`):

- **Claude timeout would hurt, not help.** Among finished license calls >300s:
  17/17 produced a value, 11 correct, 0 UNKNOWN; >360s: 4/4 correct. Slow Claude
  calls are doing real work, not hanging. A 300s cap converts correct Hits →
  UNKNOWN (accuracy regression). Rejected as the fix.
- **The GPT-4.1 copyright extract is pathologically slow.** copyright wall by
  path: web(2nd Opus) 241s mean, npm 126s, **file-only (GPT extract only) 119s
  mean / 109s median / 493s max**. The client is `timeout=60, max_retries=0`, so
  a single successful call is **≤60s by construction** — a 109s median proves
  most extract calls **time out at 60s and retry**, or their coroutine is
  **starved**. This step runs for ~all 221 components.

## (c) Single highest-leverage fix (revised)

**Fix the GPT-4.1 copyright-extract latency — start by constructing one shared
`Gpt41Client` instead of a fresh one per call in `copyright.py`.** Each
`Gpt41Client()` builds a blocking `DefaultAzureCredential` with no token cache
or connection pooling; per-call construction forces a fresh, event-loop-blocking
AAD token fetch on every component, which both adds latency and stalls all 30
workers (explaining avg concurrency 20.4 < peak 30). old_code builds one shared
client (and the new-code *equality* path already shares one) — only copyright
regressed.

Leverage: ~109s median × nearly every component; plausibly ~100s/component and a
real concurrency lift — an order of magnitude more than the tail-timeout idea.

Cheap confirmation before coding (untested here): log GPT-4.1 attempt count +
per-attempt latency (or count `APITimeoutError`) for one extract; and time
`Gpt41Client()` construction / first token fetch. If attempts>1 or construction
is seconds, the diagnosis holds.

Secondary (not applied): raise/verify the 60s GPT timeout; offload credential/
token acquisition off the event loop; restore fine-grained semaphore pools; add
a high (~900–1200s) Claude safety-net timeout for true hangs (never 300s).
