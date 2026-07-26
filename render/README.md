# Render Workflows — self-heal orchestration

Real six-stage self-heal, wired as Render Workflows tasks. Separate from
`../workflows/` (Lawrence's connectivity spike — do not merge these).

- **Assumes** a ShipFast mock is already running and already broke on v3 —
  this service does not start/stop the mock or touch git state. Use
  `scripts/demo.sh` (steps 1-4) to get a mock into that state first, or
  point at your own.
- Tasks: `detect_break`, `regenerate_adapter`, `verify_healed`, `evidence`,
  and the orchestrator `self_heal` that chains all four.

## Local run (no Render account required)

From this `render/` directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# terminal A — task server on a different port than Lawrence's spike (8120)
render workflows dev --port 8121 -- .venv/bin/python main.py

# terminal B — get a mock into the broken-v3 state, e.g. by running
# scripts/demo.sh from the repo root and letting it stop at STEP 5 (it
# leaves the mock running and broken on v3 until you Ctrl-C it)

render workflows tasks runs start detect_break --local \
  --input='["http://127.0.0.1:8081"]' -o json
# -> expect {"broken": true, ...}

render workflows tasks runs start self_heal --local \
  --input='["http://127.0.0.1:8081"]' -o json
# -> this one actually shells out to scripts/pdd_regen.sh (a real PDD call)
```

## Cloud deploy (for hackathon submission proof)

Needs, beyond this service:

1. **A public mock.** `../mock/server.py` deployed as its own Render Web
   Service (build: `pip install -r ../mock/requirements.txt` or equivalent;
   run: `uvicorn mock.server:app --host 0.0.0.0 --port $PORT`) so
   `mock_base_url` isn't `localhost`.
2. **`pdd-cli` in the build.** It's a global tool on dev machines today, not
   in `pyproject.toml` — add `uv tool install pdd-cli` (or `pip install
   pdd-cli`) to the build command.
3. **An LLM API key** for `pdd-cli`, set as a Render secret env var (check
   your local `pdd` setup for which one it reads).

```bash
render login
render workspace set

render workflows create \
  --name self-heal-orchestration \
  --runtime python \
  --build-command "pip install -r render/requirements.txt && uv tool install pdd-cli" \
  --run-command ".venv/bin/python render/main.py" \
  --repo . \
  --region oregon \
  -o json

render workflows tasks runs start self_heal \
  --input='["https://<your-deployed-mock>.onrender.com"]' -o json
# -> note the run id as submission proof
```
