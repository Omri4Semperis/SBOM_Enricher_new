# DECISIONS — freeze-prevention changes (run 380 event-loop wedge)

Status: IN PROGRESS (grilling). Decisions land here as each branch resolves.

## Subject

Harden the enrichment pipeline against the whole-event-loop freeze observed in
run `20260716_102127_ClaudeOpu-4-8_380` (stalled at 308/380, 0 CPU, timeouts
never fired). Scope = defensive changes to `src/`, not a rearchitecture.

## Root cause (established this session)

The single asyncio event loop was blocked by a synchronous call on the loop
thread — prime suspect: the synchronous Azure credential/token provider
(`azure.identity.get_bearer_token_provider(DefaultAzureCredential(), …)`) used
by `Gpt41Client`. A blocked loop also freezes every timeout, so `timeout=60` on
the GPT client never fired.

## Governing principle (ponytail)

Every await on an external resource must be bounded, and no blocking call may
run on the loop thread. If that holds, the loop cannot wedge and no worker can
hang forever — so no separate watchdog/supervisor is needed.

## Branch checklist

- [x] 1. Goals & non-goals
- [x] 2. Root-cause fix: async credential provider
- [x] 3. Deadlines: GPT + Claude subprocess safety-net
- [x] 4. Subprocess cleanup on timeout
- [x] 5. Liveness watchdog
- [x] 6. Concurrency shape
- [x] 7. Resumability after a kill
- [x] 8. Testing
- [x] 9. Open risks / deferrals

## Decisions

1. **Scope = liveness only.** The run must always make progress or die loudly
   with diagnostics; never silently freeze. Throughput and accuracy are out of
   scope (covered in `perf_analysis_20260716_run380.md`).

2. **Root-cause fix: async Azure credentials.** In `gpt41_client.py`, import
   `DefaultAzureCredential` + `get_bearer_token_provider` from
   `azure.identity.aio` (confirmed present, v1.25.3) instead of `azure.identity`.
   The token fetch becomes an awaited coroutine, so it can no longer block the
   loop thread. One shared client per run (already refactored in the tree), so
   this happens once, not per component. Perf impact: removes the whole-loop
   freeze and the avg-concurrency-20.4-vs-30 gap.

3. **Claude subprocess wall-clock cap = 1200s, fail-closed, no retry.** Wrap
   `proc.communicate()` in `asyncio.wait_for(..., 1200)`. On timeout: `proc.kill()`
   then `await proc.wait()`, then raise `HardFailure` → component copyright/
   license falls to UNKNOWN. Value rationale (from finished data): healthy Claude
   calls maxed ~536s; the frozen procs ran 1–3h — 1200s cleanly separates them.
   NEVER 300s: report shows license calls >360s were 4/4 correct, so a low cap
   destroys correct results. Fail-closed (not transient/retry) because retrying a
   20-minute hang 3× would hog a slot for an hour.

4. **GPT deadlines: no change.** Client already `timeout=60, max_retries=0`
   wrapped by `retry.py` (≤3 transient attempts) → bounded ~190s. Once creds are
   async, that 60s actually fires. Nothing to add.

5. **No watchdog.** Follows from the governing principle: with async creds +
   every external await bounded (GPT ✓, Claude ✓ via #3, HTTP ✓ in threads with
   timeouts), the loop cannot wedge, so a separate-process watchdog + supervisor
   + resume is speculative infra for an already-closed failure class. (Overrule
   if belt-and-suspenders is wanted.)

6. **Concurrency shape: no change** (single `Semaphore(30)`). The sem already
   reached 30; the avg<peak gap was the blocking-cred artifact that #2 removes.
   A separate GPT pool is speculative tuning and out of scope.

7. **Resumability: rely on existing mechanisms.** CSV rows already flush via
   `as_completed`; per-component cache already written. No new resume machinery —
   the fix means we won't routinely kill mid-run.

8. **Testing: one check.** Unit test for the Claude timeout path — a fake
   subprocess that exceeds the cap must be killed and produce fail-closed UNKNOWN
   with no retry.

## Deferred (with triggers)

- **Download slow-drip slot-hogging.** `requests` timeout is inactivity-only, so
  a trickling server can hold a worker slot (the 732s outlier). Clean fix = move
  that GET to `httpx` with a total timeout. Deferred: rare tail event, only hogs
  one slot (doesn't freeze the loop). Add if tail latency becomes a problem.
  `ponytail: requests inactivity-timeout, switch to httpx total-timeout if slow-drip recurs`
- **Watchdog** — deferred/rejected per decision 5; revisit only if a future
  change reintroduces a blocking call on the loop thread.
