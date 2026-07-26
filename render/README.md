# Render Workflows — self-heal orchestration

Real six-stage self-heal, wired as Render Workflows tasks. Separate from
`../workflows/` (Lawrence's connectivity spike — do not merge these).

- **Assumes** a ShipFast mock is already running and already broke on v3 —
  this service does not start/stop the mock or touch git state. Use
  `scripts/demo.sh` (steps 1-4) to get a mock into that state first, or
  point at your own.
- Tasks: `detect_break`, `regenerate_adapter`, `verify_healed`, `evidence`,
  and the orchestrator `self_heal` that chains all four.

`render-sdk` and `pdd-cli` are real dependencies in the repo root
`pyproject.toml` / `uv.lock` — no separate install step needed either
locally or in the cloud build. `regenerate_adapter` calls
`scripts/pdd_regen.sh`, which itself runs `uv run pdd ...`, so it resolves
`pdd-cli` from this same project environment.

## Local run (no Render account required)

From the repo root:

```bash
# terminal A — task server on a different port than Lawrence's spike (8120)
render workflows dev --port 8121 -- uv run -- python render/main.py

# terminal B — get a mock into the broken-v3 state, e.g. by running
# scripts/demo.sh and letting it stop at STEP 5 (it leaves the mock running
# and broken on v3 until you Ctrl-C it)

render workflows tasks runs start detect_break --local \
  --input='["http://127.0.0.1:8081"]' -o json
# -> expect {"broken": true, ...}

render workflows tasks runs start self_heal --local \
  --input='["http://127.0.0.1:8081"]' -o json
# -> this one actually shells out to scripts/pdd_regen.sh (a real PDD call)
```

## Cloud deploy (for hackathon submission proof)

The workflow service itself (`self-healing-integrations`,
`wfl-d9im9n3eo5us73a5qa00`) already exists in the Render dashboard, repo
root, build command `uv sync --frozen && uv cache prune --ci`. Run command
must be set to:

```
uv run -- python render/main.py
```

Still needed beyond that:

1. **A public mock.** `../mock/server.py` deployed as its own Render Web
   Service so `mock_base_url` isn't `localhost`.
2. **An LLM API key** for `pdd-cli`, set as a Render secret env var on the
   workflow service (check your local `pdd` setup for which one it reads).

```bash
render workflows tasks runs start self_heal \
  --input='["https://<your-deployed-mock>.onrender.com"]' -o json
# -> note the run id as submission proof
```
