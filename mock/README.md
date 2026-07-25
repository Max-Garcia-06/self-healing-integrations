# ShipFast mock vendor API

Fake shipping carrier serving two incompatible rates API versions off the
same fake data. Demonstrates a vendor breaking change: `/v3/rates` renames
fields, restructures price, and requires a new header.

## Start

```bash
uvicorn mock.server:app --port 8080
```

Live version defaults to `v2`. Override at startup:

```bash
SHIPFAST_VERSION=v3 uvicorn mock.server:app --port 8080
```

## Quote against v2 (default live version)

```bash
curl -s -X POST http://localhost:8080/v2/rates \
  -H "Content-Type: application/json" \
  -d '{
    "parcel": {"length_in": 12, "width_in": 8, "height_in": 6, "weight_lb": 4},
    "destination": {
      "address1": "123 Main St",
      "city": "Springfield",
      "state": "IL",
      "postal_code": "62704",
      "country": "US"
    }
  }'
```

## Check / flip the live version

```bash
curl -s http://localhost:8080/admin/version

curl -s -X POST http://localhost:8080/admin/version \
  -H "Content-Type: application/json" \
  -d '{"version": "v3"}'
```

Once flipped, `/v2/rates` starts returning `410 Gone` and `/v3/rates` goes
live.

## Quote against v3 (requires X-Shipper-Id header)

```bash
curl -s -X POST http://localhost:8080/v3/rates \
  -H "Content-Type: application/json" \
  -H "X-Shipper-Id: shipper-123" \
  -d '{
    "parcel": {"length_in": 12, "width_in": 8, "height_in": 6, "weight_lb": 4},
    "destination": {
      "address1": "123 Main St",
      "city": "Springfield",
      "state": "IL",
      "postal_code": "62704",
      "country": "US"
    }
  }'
```

Without `X-Shipper-Id`, v3 returns `400` with an error body. While `v2` is
still live, `/v3/rates` returns `410 Gone`.
