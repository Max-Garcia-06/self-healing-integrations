# Render Workflows — connectivity spike

Minimal, self-contained proof that we can define and run a real Render Workflows
task. It exists only to de-risk Render for the project.

- **Not** wired to ShipFast.
- **Not** the six-stage self-healing workflow.
- One trivial task: `verify_render_connection`.

## What's here

| File | Purpose |
|------|---------|
| `main.py` | Render Workflows service defining the `verify_render_connection` task. |
| `requirements.txt` | Single dependency: `render_sdk>=0.6.0`. |
| `.gitignore` | Ignores `.venv/`, build output, logs, secrets. |

The task takes an integration id and returns a fixed payload:

```json
{
  "integrationId": "shipfast",
  "status": "ok",
  "message": "Render Workflows connection verified"
}
```

## Prerequisites

- **Render CLI ≥ 2.12.0** (Workflows requires it; verified with `v2.22.0`).
  Install the official binary (macOS arm64 shown) or use Homebrew:

  ```bash
  # Direct binary (no auth, no account needed)
  curl -fsSL -o /tmp/render.zip \
    https://github.com/render-oss/cli/releases/download/v2.22.0/cli_2.22.0_darwin_arm64.zip
  unzip -o /tmp/render.zip -d /tmp/render-cli
  mkdir -p "$HOME/.local/bin"
  cp /tmp/render-cli/cli_v2.22.0 "$HOME/.local/bin/render"
  chmod +x "$HOME/.local/bin/render"
  export PATH="$HOME/.local/bin:$PATH"
  render --version
  ```

- **Python 3.11+** (validated on 3.14.2).

## Local run (no Render account required)

From this `workflows/` directory:

```bash
# 1. Create an isolated venv and install the SDK
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Start the local task server (terminal A) — listens on port 8120
render workflows dev --port 8120 -- .venv/bin/python main.py

# 3. In terminal B: confirm the task is registered
render workflows tasks list --local -o json

# 4. Start a run. --input is a JSON ARRAY of positional args.
#    verify_render_connection(integration_id) -> ["shipfast"]
render workflows tasks runs start verify_render_connection \
  --local --input='["shipfast"]' -o json
# -> note the returned run id, e.g. trn-...

# 5. Inspect the completed run and its result
render workflows tasks runs show <trn-id> --local -o json
```

Expected `results` in the completed run:

```json
[{ "integrationId": "shipfast", "status": "ok", "message": "Render Workflows connection verified" }]
```

## Cloud deploy (requires a Render account — NOT done in this spike)

Cloud deployment needs (a) an authenticated CLI and (b) this repo reachable at a
Git remote. Neither is set up here, so the cloud run is **unverified**.

```bash
# One-time interactive browser auth (cannot be automated):
render login
render workspace set

# Deploy from the current repo's origin remote:
render workflows create \
  --name self-healing-verify \
  --runtime python \
  --build-command "pip install -r workflows/requirements.txt" \
  --run-command ".venv/bin/python workflows/main.py" \
  --repo . \
  --region oregon \
  -o json

# Then trigger a cloud run (omit --local):
render workflows tasks runs start verify_render_connection --input='["shipfast"]' -o json
```

> For automated/CI auth instead of `render login`, set `RENDER_API_KEY` (never
> commit it; use an env var or an ignored `.env`).
