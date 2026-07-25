"""Mock ShipFast vendor API — serves incompatible v2 and v3 rates endpoints.

Demo infrastructure: hand-written, not generated. Simulates a shipping carrier
that ships a breaking API change (v3) while v2 is still nominally "current"
until an admin flips the live version.

Request and response shapes are kept EXACTLY in step with the pinned snapshots
in context/specs/shipfast/. The snapshot is the source of truth; if these two
disagree the adapter fails for reasons that have nothing to do with the heal.
"""
import os

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="ShipFast Mock API")

VALID_VERSIONS = {"v2", "v3"}
_live_version = os.environ.get("SHIPFAST_VERSION", "v2")
if _live_version not in VALID_VERSIONS:
    _live_version = "v2"


class Parcel(BaseModel):
    weight_oz: int = Field(gt=0)
    length_in: float = Field(gt=0)
    width_in: float = Field(gt=0)
    height_in: float = Field(gt=0)


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


# service_code -> (base_cents, cents_per_lb, transit_mode, service_name, estimated_days)
SERVICE_TABLE = {
    "GND_ECON": (550, 205, "ground", "Ground Economy", 7),
    "GND": (795, 142, "ground", "Ground Standard", 5),
    "AIR_2DAY": (1450, 310, "air", "Air 2-Day", 2),
    "AIR_NEXT": (2600, 380, "air", "Air Next Day", 1),
    "FREIGHT": (4000, 90, "freight", "Freight LTL", 6),
}


def quote_services(weight_oz: int) -> list[dict]:
    weight_lb = weight_oz / 16.0
    services = []
    for code, (base_cents, cents_per_lb, transit_mode, name, days) in SERVICE_TABLE.items():
        price_cents = base_cents + round(cents_per_lb * weight_lb)
        services.append(
            {
                "service_code": code,
                "service_name": name,
                "price_cents": price_cents,
                "currency": "USD",
                "transit_mode": transit_mode,
                "estimated_days": days,
            }
        )
    return services


def retired_response(version: str) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "code": "version_retired",
            "message": f"API version {version} has been retired. "
            f"Current live version is {_live_version}.",
        },
    )


@app.post("/v2/rates")
async def rates_v2(body: RateRequest):
    if _live_version != "v2":
        return retired_response("v2")
    return {"request_id": "mock-v2", "rates": quote_services(body.parcel.weight_oz)}


@app.post("/v3/rates")
async def rates_v3(body: RateRequest, x_shipper_id: str | None = Header(default=None)):
    if _live_version != "v3":
        return retired_response("v3")
    if not x_shipper_id:
        raise HTTPException(
            status_code=400,
            detail="X-Shipper-Id header is required for v3 API",
        )
    v3_rates = [
        {
            "service_level": s["service_code"],
            "service_name": s["service_name"],
            "amount": {"value": s["price_cents"], "currency": s["currency"]},
            "transit_mode": s["transit_mode"],
            "estimated_days": s["estimated_days"],
        }
        for s in quote_services(body.parcel.weight_oz)
    ]
    return {"request_id": "mock-v3", "rates": v3_rates}


@app.get("/admin/version")
async def get_version():
    return {"version": _live_version}


@app.post("/admin/version")
async def set_version(body: VersionUpdate):
    global _live_version
    if body.version not in VALID_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"version must be one of {sorted(VALID_VERSIONS)}",
        )
    _live_version = body.version
    return {"version": _live_version}
