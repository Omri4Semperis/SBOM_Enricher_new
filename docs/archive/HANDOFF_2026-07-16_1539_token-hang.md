# HANDOFF — archived Azure token-hang investigation

- Archived: 2026-07-16
- Objective: Diagnose stalls in runs `20260716_143027_ClaudeOpu-4-8_220` and `20260716_145224_ClaudeSon-5_220`; no root-cause fix applied.
- Repo: `C:/Users/OmriNardiNiri/Documents/_Dev/2026-06-07 improve sbom-enricher agent/SBOM_Enricher_new`
- Branch: `master`
- HEAD at original handoff: `3ad5595`

## Findings

- In `src/gpt41_client.py`, `DefaultAzureCredential.get_token()` runs through
  `asyncio.to_thread()` without a timeout.
- A hung token request leaves a GPT operation open forever.
- `run_workers` holds a semaphore slot for the entire component. With
  `workers=20`, enough hung token requests consume every slot and make a run
  silent.

## Proposed next action from the archived handoff

Add a timeout around token acquisition and test that a hung provider retries
instead of hanging. This has not been implemented.
