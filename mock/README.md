# ShipFast mock upstream provider

Deterministic FastAPI mock of the fictional **ShipFast** rating API. It serves
two incompatible wire contracts and flips between them at runtime **without a
restart**, so an adapter pinned to the old format breaks visibly during the demo.

The committed OpenAPI documents are the sole source of truth:

| Active version | Operation | Spec file (authoritative) |
|----------------|-----------|---------------------------|
| `v2` (default) | `POST /v2/rates` | `context/specs/shipfast/openapi.snapshot.json` (`2.4.1`) |
| `v3`           | `POST /v3/rates` | `context/specs/shipfast/v3.json` (`3.0.0`) |

`GET /openapi.json` serves the exact committed document for the active version
(loaded from disk — not a hand-maintained third copy).

## What changed between v2 and v3

- **Path:** `/v2/rates` → `/v3/rates`.
- **New required header:** `X-Shipper-Id` (v3 only; omitting it → `400`).
- **Response id field:** `service_code` → `service_level`.
- **Response price:** flat `price_cents` + `currency` → nested `amount` object
  (`{ "value": <int>, "currency": <str> }`).
- Request body is **identical** across v2 and v3.

Only the active version's path is served; the inactive one returns `410 Gone`.

## Deterministic rate data

Every rate response returns the same three services, chosen so the cheapest
**ground** option is not the cheapest **overall** — this proves the adapter's
"cheapest ground" business rule:

| Service | `transit_mode` | Price (minor units) |
|---------|----------------|---------------------|
| Ground Standard (`GR_STD`) | `ground` | **1240** ← correct cheapest-ground |
| Ground Priority (`GR_PRI`) | `ground` | 1680 |
| Air Express (`AIR_EXP`)    | `air`    | 990 ← cheapest overall, must NOT be chosen |

## Install dependencies

Dependencies are declared in the repo's `pyproject.toml`; use `uv`:

```bash
uv sync
```

## Run the tests

```bash
uv run pytest mock/test_server.py -v
```

No network access or deployed service is required.

## Start the mock

Defaults to `v2` and binds `127.0.0.1:8081` (matching the spec's `servers` URL).

```bash
uv run uvicorn mock.server:app --host 127.0.0.1 --port 8081
```

Host/port are configurable either via uvicorn flags above, or via env vars when
running the module directly:

```bash
SHIPFAST_HOST=0.0.0.0 SHIPFAST_PORT=8081 uv run python mock/server.py
```

All commands below assume `BASE=http://127.0.0.1:8081`.

## Demo sequence (copy-pasteable)

```bash
BASE=http://127.0.0.1:8081

# 1. Health — reports the active version
curl -s $BASE/health
# {"status":"ok","provider":"shipfast","activeVersion":"v2"}

# 2. Fetch the active OpenAPI document (v2)
curl -s $BASE/openapi.json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
# 2.4.1

# 3. A valid v2 request (Authorization required)
curl -s -X POST $BASE/v2/rates \
  -H "Authorization: Bearer demo-key" \
  -H "Content-Type: application/json" \
  -d '{
        "account_number": "ACME-001",
        "parcel": {"weight_oz": 32, "length_in": 12, "width_in": 8, "height_in": 6},
        "destination": {"line1":"123 Main St","city":"Springfield","region":"IL","postal_code":"62704","country_code":"US"}
      }'
# 200 -> rates[] with service_code + price_cents + currency

# 4. Toggle to v3 (no restart)
curl -s -X POST $BASE/admin/version \
  -H "Content-Type: application/json" -d '{"version":"v3"}'
# {"previousVersion":"v2","activeVersion":"v3"}

# 5. The OLD v2 request now fails — the v2 contract is retired
curl -s -w "\nHTTP %{http_code}\n" -X POST $BASE/v2/rates \
  -H "Authorization: Bearer demo-key" \
  -H "Content-Type: application/json" \
  -d '{"parcel":{"weight_oz":32,"length_in":12,"width_in":8,"height_in":6},"destination":{"postal_code":"62704","country_code":"US"}}'
# {"code":"version_retired",...}  HTTP 410

# 6. Fetch the active OpenAPI document (now v3)
curl -s $BASE/openapi.json | python3 -c "import sys,json;print(json.load(sys.stdin)['info']['version'])"
# 3.0.0

# 7. A valid v3 request — requires the new X-Shipper-Id header
curl -s -X POST $BASE/v3/rates \
  -H "Authorization: Bearer demo-key" \
  -H "X-Shipper-Id: shipper-123" \
  -H "Content-Type: application/json" \
  -d '{
        "account_number": "ACME-001",
        "parcel": {"weight_oz": 32, "length_in": 12, "width_in": 8, "height_in": 6},
        "destination": {"line1":"123 Main St","city":"Springfield","region":"IL","postal_code":"62704","country_code":"US"}
      }'
# 200 -> rates[] with service_level + amount:{value,currency}

# 7b. Same v3 request WITHOUT X-Shipper-Id -> 400
curl -s -w "\nHTTP %{http_code}\n" -X POST $BASE/v3/rates \
  -H "Authorization: Bearer demo-key" \
  -H "Content-Type: application/json" \
  -d '{"parcel":{"weight_oz":32,"length_in":12,"width_in":8,"height_in":6},"destination":{"postal_code":"62704","country_code":"US"}}'
# {"code":"missing_header",...}  HTTP 400

# 8. Toggle back to v2
curl -s -X POST $BASE/admin/version \
  -H "Content-Type: application/json" -d '{"version":"v2"}'
# {"previousVersion":"v3","activeVersion":"v2"}
```

## Control endpoints

| Method & path | Purpose |
|---------------|---------|
| `GET /health` | `{status, provider, activeVersion}` |
| `GET /openapi.json` | Exact committed OpenAPI doc for the active version |
| `GET /admin/version` | `{version}` |
| `POST /admin/version` | Body `{"version":"v2"\|"v3"}` → `{previousVersion, activeVersion}`; any other value → `400` |
