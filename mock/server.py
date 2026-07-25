"""ShipFast mock upstream provider.

Deterministic FastAPI mock of the fictional ShipFast rating API used for the
self-healing-integrations demo. It serves TWO incompatible wire contracts:

  * v2 -> POST /v2/rates      (flat price_cents + currency, service_code)
  * v3 -> POST /v3/rates      (nested amount Money, service_level, new
                               required X-Shipper-Id header)

The active version is held in memory, defaults to v2, and is flipped at runtime
via POST /admin/version WITHOUT restarting the process. Only the active
version's operation is served; the inactive one is explicitly retired (410),
so an adapter pinned to the old wire format breaks visibly after a flip.

Source of truth: this server does NOT invent schemas. The two committed OpenAPI
documents under context/specs/shipfast/ are authoritative; GET /openapi.json
serves the exact committed document for the active version, loaded from disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

# --------------------------------------------------------------------------- #
# Repository-relative spec loading (cwd-independent).
# --------------------------------------------------------------------------- #
# server.py lives at <repo>/mock/server.py, so the repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = REPO_ROOT / "context" / "specs" / "shipfast"

# Map active version -> committed OpenAPI document on disk. These files are
# teammate-owned and authoritative; we only read them.
SPEC_FILES = {
    "v2": SPEC_DIR / "openapi.snapshot.json",
    "v3": SPEC_DIR / "v3.json",
}
VALID_VERSIONS = tuple(SPEC_FILES.keys())


def _load_specs() -> dict[str, dict]:
    """Load and cache both committed OpenAPI documents, failing loudly."""
    specs: dict[str, dict] = {}
    for version, path in SPEC_FILES.items():
        if not path.exists():
            raise RuntimeError(
                f"ShipFast mock: OpenAPI spec for {version} not found at {path}. "
                f"Expected the committed snapshot under context/specs/shipfast/."
            )
        try:
            specs[version] = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"ShipFast mock: OpenAPI spec for {version} at {path} is not valid "
                f"JSON: {exc}"
            ) from exc
    return specs


# Loaded at import time so a missing/invalid spec fails the process immediately
# with a clear message instead of 500-ing on the first request.
SPECS = _load_specs()

# In-memory active version. Resets to v2 on every process start.
_active_version = "v2"

# --------------------------------------------------------------------------- #
# Deterministic rate data.
# --------------------------------------------------------------------------- #
# Fixed prices chosen so the cheapest OVERALL option (Air Express, 990) differs
# from the cheapest GROUND option (Ground Standard, 1240). This proves the
# business rule "pick the cheapest ground service", not "the cheapest service".
CURRENCY = "USD"
RATE_TABLE = [
    {"code": "GR_STD", "name": "Ground Standard", "mode": "ground", "cents": 1240, "days": 5},
    {"code": "GR_PRI", "name": "Ground Priority", "mode": "ground", "cents": 1680, "days": 3},
    {"code": "AIR_EXP", "name": "Air Express", "mode": "air", "cents": 990, "days": 1},
]

# --------------------------------------------------------------------------- #
# Request models (identical across v2 and v3 per the committed specs).
# Required fields have no default; optional fields default to None. Extra/unknown
# keys are ignored (matching the open OpenAPI object schemas), NOT aliased.
# --------------------------------------------------------------------------- #
class Parcel(BaseModel):
    weight_oz: int
    length_in: float
    width_in: float
    height_in: float


class Address(BaseModel):
    postal_code: str
    country_code: str
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    region: str | None = None


class RateRequest(BaseModel):
    parcel: Parcel
    destination: Address
    account_number: str | None = None


class VersionUpdate(BaseModel):
    version: str


app = FastAPI(
    title="ShipFast Mock API",
    # Disable FastAPI's auto-generated schema/docs so GET /openapi.json is free
    # to serve the committed vendor document instead.
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


def _error(status: int, code: str, message: str) -> JSONResponse:
    """Error body shaped exactly like the committed Error schema {code,message}."""
    return JSONResponse(status_code=status, content={"code": code, "message": message})


def _require_auth(request: Request) -> JSONResponse | None:
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return _error(
            401,
            "unauthorized",
            "Missing or malformed Authorization header. Expected 'Bearer <api_key>'.",
        )
    return None


async def _parse_body(request: Request) -> tuple[RateRequest | None, JSONResponse | None]:
    try:
        payload = await request.json()
    except Exception:
        return None, _error(400, "malformed_request", "Request body must be valid JSON.")
    try:
        return RateRequest.model_validate(payload), None
    except ValidationError as exc:
        return None, _error(
            400,
            "malformed_request",
            f"Request body does not match the RateRequest schema: {exc.error_count()} error(s).",
        )


def _rates_v2() -> dict:
    return {
        "request_id": "req_v2_demo",
        "rates": [
            {
                "service_code": r["code"],
                "service_name": r["name"],
                "transit_mode": r["mode"],
                "price_cents": r["cents"],
                "currency": CURRENCY,
                "estimated_days": r["days"],
            }
            for r in RATE_TABLE
        ],
    }


def _rates_v3() -> dict:
    return {
        "request_id": "req_v3_demo",
        "rates": [
            {
                "service_level": r["code"],
                "service_name": r["name"],
                "transit_mode": r["mode"],
                "amount": {"value": r["cents"], "currency": CURRENCY},
                "estimated_days": r["days"],
            }
            for r in RATE_TABLE
        ],
    }


# --------------------------------------------------------------------------- #
# Provider operations. Each path is served ONLY while its version is active; the
# inactive contract is explicitly retired with 410 so a stale adapter breaks.
# --------------------------------------------------------------------------- #
@app.post("/v2/rates")
async def rates_v2(request: Request):
    if _active_version != "v2":
        return _error(
            410,
            "version_retired",
            "The /v2/rates contract has been retired. Active version is "
            f"{_active_version}. Use /{_active_version}/rates.",
        )
    if (err := _require_auth(request)) is not None:
        return err
    _, err = await _parse_body(request)
    if err is not None:
        return err
    return _rates_v2()


@app.post("/v3/rates")
async def rates_v3(request: Request):
    if _active_version != "v3":
        return _error(
            410,
            "version_retired",
            "The /v3/rates contract is not active. Active version is "
            f"{_active_version}. Use /{_active_version}/rates.",
        )
    if (err := _require_auth(request)) is not None:
        return err
    # X-Shipper-Id became mandatory in v3; omission is a 400 per the spec.
    if not request.headers.get("X-Shipper-Id"):
        return _error(
            400,
            "missing_header",
            "X-Shipper-Id header is required as of v3.",
        )
    _, err = await _parse_body(request)
    if err is not None:
        return err
    return _rates_v3()


# --------------------------------------------------------------------------- #
# Control endpoints (outside the OpenAPI operations).
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health():
    return {"status": "ok", "provider": "shipfast", "activeVersion": _active_version}


@app.get("/openapi.json")
async def active_openapi():
    """Serve the exact committed OpenAPI document for the active version."""
    return JSONResponse(content=SPECS[_active_version])


@app.get("/admin/version")
async def get_version():
    return {"version": _active_version}


@app.post("/admin/version")
async def set_version(body: VersionUpdate):
    global _active_version
    if body.version not in VALID_VERSIONS:
        return _error(
            400,
            "invalid_version",
            f"version must be one of {list(VALID_VERSIONS)}.",
        )
    previous = _active_version
    _active_version = body.version
    return {"previousVersion": previous, "activeVersion": _active_version}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SHIPFAST_HOST", "127.0.0.1")
    port = int(os.environ.get("SHIPFAST_PORT", "8081"))
    uvicorn.run(app, host=host, port=port)
