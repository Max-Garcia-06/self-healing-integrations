# Self-Healing Integrations — dashboard

A minimal React + TypeScript + Vite dashboard that visualizes the existing
terminal demo (`scripts/demo.sh`). It does **not** reimplement any healing
logic — a small FastAPI backend runs the real script and turns its terminal
output into live Server-Sent Events.

```
frontend/            React + Vite dashboard (this dir)
../backend/demo_api.py   FastAPI backend: runs scripts/demo.sh, streams events
```

## Run it (two terminals)

**1. Backend** (from the repo root):

```bash
uv run uvicorn backend.demo_api:app --host 127.0.0.1 --port 8000
```

**2. Frontend** (from `frontend/`):

```bash
npm install        # first time only
npm run dev        # http://localhost:5173  (proxies /api -> :8000)
```

Open <http://localhost:5173> and click **Run Healing Demo**.

## What you'll see

The seven workflow steps light up live from the real run:

1. Baseline provider — mock starts on v2
2. Baseline adapter — generated v2 adapter returns **Ground Standard, 1240 USD**
3. Vendor API change — provider switched to v3
4. Integration breaks — stale adapter rejected (**410 / NoServiceAvailable**) —
   shown as an *expected* break, not a demo failure
5. PDD regeneration — adapter regenerated from the durable prompt
6. Integration healed — regenerated adapter returns **1240 USD** on v3
7. Evidence verified — prompt **unchanged**, spec **changed**, adapter
   **changed**, business result **preserved**

Plus a result panel, an evidence panel, and collapsible **spec** and **adapter**
diffs. All values come from the real run — nothing is hard-coded.

## Requirement: PDD must be authenticated for steps 5–7

Steps 1–4 always work. Steps 5–7 run the real `pdd` regeneration, which needs
model access. If PDD is not authenticated, the dashboard honestly shows the
regeneration step **failing** (it does not fake a heal). To get the full green
run, whoever has PDD access must authenticate first:

```bash
pdd auth login        # or export a supported model API key
```

Then re-run from the dashboard.

## Scripts

```bash
npm run dev         # dev server with API proxy
npm run typecheck   # tsc --noEmit
npm run build       # typecheck + production build to dist/
npm run preview     # serve the production build (no API proxy)
```

## Notes

- One run at a time; a second concurrent run returns HTTP 409.
- The backend runs the demo in its own process group and signals it on
  timeout/shutdown, so `scripts/demo.sh`'s own cleanup restores the mock to v2
  and never leaves a subprocess running.
- If the event stream drops, the page stays usable and shows the last state;
  use **Reset** to start over.
