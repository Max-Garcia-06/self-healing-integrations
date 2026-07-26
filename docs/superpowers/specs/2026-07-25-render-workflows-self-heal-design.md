# Render Workflows self-heal orchestration

## Purpose

Wire the six-stage self-healing flow (already proven by `scripts/demo.sh`) into a
real Render Workflows service, on Max's side of the repo, separate from
Lawrence's `workflows/` connectivity spike. Needed to demonstrate genuine
multi-task use of Render Workflows for hackathon prize qualification.

## Scope

- New `render/` directory (neutral, not `workflows/`).
- Assumes the vendor break already exists — input is a running ShipFast mock
  URL already switched to v3. The workflow's job is to detect the break,
  heal it, and prove the heal, not to manage mock lifecycle or git baseline
  resets (that stays `scripts/demo.sh`'s job for the interactive demo).
- Wraps existing scripts (`scripts/run_adapter.py`, `scripts/pdd_regen.sh`)
  via subprocess. No adapter or PDD logic duplicated.

## Architecture

One Render Workflows service (`render/main.py`), four leaf tasks, one
orchestrator task that chains them (Render SDK: a task calling another
`@app.task` function triggers a chained run, `await`ed).

### Tasks

- `detect_break(mock_base_url)` — runs the adapter against the mock, confirms
  it fails, snapshots current `adapter.py` + `.prompt` file contents for the
  later diff.
- `regenerate_adapter()` — runs `scripts/pdd_regen.sh`.
- `verify_healed(mock_base_url)` — runs the adapter again, confirms
  `1240 USD`.
- `evidence(adapter_before, prompt_before)` — diffs prompt intent (pin lines
  stripped, same rule as `demo.sh`'s `intent()`), confirms the adapter
  changed, confirms the two committed vendor spec files differ.
- `self_heal(mock_base_url)` — orchestrator: `detect_break` → skip if not
  broken → `regenerate_adapter` → fail fast if regen fails → `verify_healed`
  + `evidence` → final verdict.

### Data flow

`detect_break`'s before-snapshots pass forward as explicit arguments to
`evidence` — no shared filesystem assumed between task runs, since cloud
task runs may land on different machines.

### Error handling

Leaf tasks return a status dict (`ok` / `broken` / `healed` boolean + raw
output) and never raise for expected business failures — mirrors
`run_adapter.py`'s existing `ADAPTER_OK` / `ADAPTER_ERROR` / `ADAPTER_FATAL`
contract. The orchestrator short-circuits on a regen failure and returns
partial evidence rather than crashing.

## Deploy targets

**Local** (no account needed): `render workflows dev`, same pattern as
Lawrence's spike. Verifies task wiring against a demo mock already forced
into the broken v3 state by `scripts/demo.sh` steps 1-4.

**Cloud** (for hackathon proof): needs two things beyond the workflow
service itself —

1. A publicly reachable mock. `mock/server.py` (neutral dir, not Lawrence's
   `mock_upstream/`) deployed as its own small Render Web Service, so
   `mock_base_url` is not `localhost`.
2. A build command that installs `pdd-cli` (it's a global tool on Max's
   machine today, not a `pyproject.toml` dependency) plus whatever LLM API
   key `pdd-cli` needs, set as a Render secret env var.

## Explicit boundary

No `pdd` subcommand is run directly by the assistant, even indirectly via
triggering `regenerate_adapter` or `self_heal` runs — per repo rule. Those
runs are triggered by Max. `detect_break` and `verify_healed` don't touch
`pdd` and can be exercised directly.

## Testing

- Local: `render workflows tasks runs start detect_break --local
  --input='["http://127.0.0.1:8081"]'` and same for `verify_healed`, against
  a mock already forced into the v2-pass/v3-break sequence.
- Cloud: deploy, trigger `self_heal` against the deployed mock URL, capture
  the run id as submission proof.
