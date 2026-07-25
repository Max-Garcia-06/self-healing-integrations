"""Mock-owned tests for the ShipFast mock provider.

These exercise the mock over the in-process ASGI app only (FastAPI TestClient).
No deployed Render service and no external network access are required.

Placed inside mock/ so pytest prepends this directory to sys.path and
`import server` resolves to mock/server.py (avoiding any collision with a
`mock` package name on the path).
"""
import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)

AUTH = {"Authorization": "Bearer test-key"}
SHIPPER = {"X-Shipper-Id": "shipper-123"}

VALID_BODY = {
    "account_number": "ACME-001",
    "parcel": {"weight_oz": 32, "length_in": 12, "width_in": 8, "height_in": 6},
    "destination": {
        "line1": "123 Main St",
        "city": "Springfield",
        "region": "IL",
        "postal_code": "62704",
        "country_code": "US",
    },
}


@pytest.fixture(autouse=True)
def reset_version():
    """Every test starts from a clean v2 process state."""
    server._active_version = "v2"
    yield
    server._active_version = "v2"


def _set_version(version: str):
    return client.post("/admin/version", json={"version": version})


# 1. Health reports v2 on startup.
def test_health_reports_v2_on_startup():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "provider": "shipfast", "activeVersion": "v2"}


# 2. Active OpenAPI endpoint returns the v2 document.
def test_openapi_returns_v2_document():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["info"]["version"] == "2.4.1"
    assert "/v2/rates" in doc["paths"]
    assert "/v3/rates" not in doc["paths"]


# 3. A valid v2 provider request succeeds with the exact v2 wire shape.
def test_valid_v2_request_succeeds():
    resp = client.post("/v2/rates", headers=AUTH, json=VALID_BODY)
    assert resp.status_code == 200
    body = resp.json()
    rates = body["rates"]
    assert len(rates) == 3
    first = rates[0]
    # v2 uses flat price_cents + currency and service_code.
    assert set(first) >= {"service_code", "service_name", "transit_mode", "price_cents", "currency"}
    assert "amount" not in first
    assert "service_level" not in first
    # Business rule fixture: cheapest ground is Ground Standard @ 1240,
    # cheapest overall is Air Express @ 990.
    ground = [r for r in rates if r["transit_mode"] == "ground"]
    cheapest_ground = min(ground, key=lambda r: r["price_cents"])
    cheapest_overall = min(rates, key=lambda r: r["price_cents"])
    assert cheapest_ground["service_name"] == "Ground Standard"
    assert cheapest_ground["price_cents"] == 1240
    assert cheapest_overall["service_name"] == "Air Express"
    assert cheapest_overall["price_cents"] == 990


# 4. Switching from v2 to v3 succeeds and reports both versions.
def test_switch_v2_to_v3():
    resp = _set_version("v3")
    assert resp.status_code == 200
    assert resp.json() == {"previousVersion": "v2", "activeVersion": "v3"}
    assert client.get("/admin/version").json() == {"version": "v3"}


# 5. Active OpenAPI endpoint then returns the v3 document.
def test_openapi_returns_v3_after_switch():
    _set_version("v3")
    doc = client.get("/openapi.json").json()
    assert doc["info"]["version"] == "3.0.0"
    assert "/v3/rates" in doc["paths"]
    assert "/v2/rates" not in doc["paths"]


# 6. The previously valid v2 request fails under v3 (retired path -> 410).
def test_old_v2_request_fails_under_v3():
    _set_version("v3")
    resp = client.post("/v2/rates", headers=AUTH, json=VALID_BODY)
    assert resp.status_code == 410
    assert resp.json()["code"] == "version_retired"


# 7. A valid v3 request with all required headers succeeds with the v3 wire shape.
def test_valid_v3_request_succeeds():
    _set_version("v3")
    resp = client.post("/v3/rates", headers={**AUTH, **SHIPPER}, json=VALID_BODY)
    assert resp.status_code == 200
    rates = resp.json()["rates"]
    first = rates[0]
    # v3 uses nested amount Money and service_level; flat fields are gone.
    assert set(first) >= {"service_level", "service_name", "transit_mode", "amount"}
    assert "price_cents" not in first
    assert "service_code" not in first
    assert set(first["amount"]) == {"value", "currency"}
    cheapest_ground = min(
        (r for r in rates if r["transit_mode"] == "ground"),
        key=lambda r: r["amount"]["value"],
    )
    assert cheapest_ground["service_name"] == "Ground Standard"
    assert cheapest_ground["amount"]["value"] == 1240


# 8. A missing newly required v3 header (X-Shipper-Id) fails with 400.
def test_v3_missing_shipper_id_fails():
    _set_version("v3")
    resp = client.post("/v3/rates", headers=AUTH, json=VALID_BODY)
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_header"


# 9. Invalid version-toggle input fails with a clear 4xx.
def test_invalid_version_toggle_rejected():
    resp = _set_version("v9")
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_version"
    # State must be unchanged.
    assert client.get("/admin/version").json() == {"version": "v2"}


# 10. Switching back to v2 restores v2 behavior.
def test_switch_back_to_v2_restores_behavior():
    _set_version("v3")
    resp = _set_version("v2")
    assert resp.status_code == 200
    assert resp.json() == {"previousVersion": "v3", "activeVersion": "v2"}
    assert client.get("/health").json()["activeVersion"] == "v2"
    # v2 request works again; v3 path is now retired.
    ok = client.post("/v2/rates", headers=AUTH, json=VALID_BODY)
    assert ok.status_code == 200
    retired = client.post("/v3/rates", headers={**AUTH, **SHIPPER}, json=VALID_BODY)
    assert retired.status_code == 410


# Extra guard: missing Authorization on an active v2 request -> 401.
def test_v2_missing_auth_unauthorized():
    resp = client.post("/v2/rates", json=VALID_BODY)
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"
