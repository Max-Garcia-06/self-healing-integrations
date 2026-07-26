# Demo runbook — Self-Healing Integrations

**One command tells the whole story:**

```bash
bash scripts/demo.sh
```

That's it. The script starts its own ShipFast mock, runs the real generated
adapter, switches the vendor to v3, shows the break, regenerates, and prints the
evidence — then always cleans up (mock stopped, provider restored to v2). It
exits `0` only if the full story succeeds.

Keep it to ~90 seconds. Enlarge your terminal font first.

---

## Current status (read before presenting)

| Steps | State | Notes |
|-------|-------|-------|
| 1–4 (v2 works → switch v3 → stale adapter breaks) | **LIVE now** | Fully verified end-to-end. |
| 5–7 (regenerate → v3 adapter passes → evidence) | **Wired, gated** | Needs the two items below. |

The script **stops cleanly at STEP 5** with `TODO: insert regeneration command
here` and exits `3` until PDD is wired. Steps 1–4 still demo perfectly on their
own — that alone shows a real provider break of a real adapter.

**To light up steps 5–7, two things are needed (owner: Max):**
1. **Wire the PDD command.** Set `PDD_REGEN_CMD` near the top of
   `scripts/demo.sh` to the real regeneration command once `.pddrc`/`.pdd`
   exist (none in the repo today). Example shape only — do not guess the real
   one: `PDD_REGEN_CMD='pdd sync integrations/shipfast/adapter.prompt'`.
2. **Fix the v3 auth header.** The v3 spec requires header `X-Shipper-Id`, but
   `src/config/shipfast.py::vendor_headers()` currently emits
   `X-ShipFast-Shipper-Id`. Verified: the mock returns **400** for the current
   header and **200** for `X-Shipper-Id`. Until `vendor_headers()` sends
   `X-Shipper-Id` on v3, the regenerated adapter (STEP 6) will 400. The mock is
   correct per the committed spec and must not be changed to accept the old
   name.

---

## What to say, step by step

Run `bash scripts/demo.sh` and narrate:

- **STEP 1 — mock starts on v2.**
  "Here's our vendor, ShipFast, live on its v2 API."

- **STEP 2 — generated v2 adapter passes.**
  Audience sees `✓ PASS / Ground Standard / 1240 USD`.
  "Our adapter — generated from a prompt — asks for a quote. The rule is
  *cheapest **ground** service*. Air is cheaper at 990, but it's not ground, so
  the correct answer is Ground Standard at **1240**."

- **STEP 3 — vendor switches to v3.**
  "Now ShipFast ships a breaking change: new endpoint, renamed price field, a
  newly required header."

- **STEP 4 — stale adapter breaks.**
  Audience sees `✓ EXPECTED FAILURE / 410 Gone / Vendor contract changed`.
  "The old adapter is pinned to v2. It breaks immediately and honestly — no
  silent wrong answers."

- **STEP 5 — regenerate.**
  "We re-run PDD against the new spec. The durable prompt — our *intent* —
  doesn't change; only the pinned vendor spec does."
  *(Today this is where the script stops with a TODO — see status table.)*

- **STEP 6 — regenerated adapter passes on v3.**
  "Same business question, new wire format, and we're back to **1240 USD**."

- **STEP 7 — evidence.**
  "Four facts: prompt intent **unchanged**, vendor spec **changed**, generated
  adapter **changed**, business rule **preserved**. That's the self-heal."

Closing line: **"The intent stayed fixed. The integration healed itself."**

---

## The key numbers (so you can not fumble them)

- Cheapest **ground** = **Ground Standard = 1240 USD** ← the correct answer.
- Cheapest **overall** = Air Express = 990 USD ← the trap; never chosen.
- Second ground = Ground Priority = 1680 USD.

---

## If something goes wrong live

- **Port already in use:** the script refuses to run and tells you. Free port
  8081 (`lsof -i :8081`) and re-run. It never demos against an unknown server.
- **You Ctrl-C mid-run:** cleanup still runs — the mock is stopped and the
  provider is restored to v2. Safe to just re-run.
- **Fallback if the harness misbehaves:** the same story by hand from
  `mock/README.md` (curl v2 → toggle v3 → curl v2 shows 410 → curl v3), plus
  `uv run pytest mock/test_server.py` for green tests.
- **No colors wanted** (e.g. recording): `NO_COLOR=1 bash scripts/demo.sh`.

---

## What's under the hood (for questions)

- `scripts/demo.sh` — the harness (lifecycle, steps, evidence, cleanup).
- `scripts/run_adapter.py` — calls the real `get_quote()` once and reports the
  result; it does not reimplement adapter logic.
- `mock/server.py` — the ShipFast mock (serves the committed v2/v3 OpenAPI docs;
  `POST /admin/version` flips the active contract at runtime).
- Adapter interface used: `integrations.shipfast.adapter.get_quote(parcel,
  destination) -> Quote`.
