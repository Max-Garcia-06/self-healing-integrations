"""Mock ShipFast vendor API — serves incompatible v2 and v3 rates endpoints.

Demo infrastructure: hand-written, not generated. Simulates a shipping carrier
that ships a breaking API change (v3) while v2 is still nominally "current"
until an admin flips the live version.
"""
import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="ShipFast Mock API")

VALID_VERSIONS = {"v2", "v3"}
_live_version = os.environ.get("SHIPFAST_VERSION", "v2")
if _live_version not in VALID_VERSIONS:
    _live_version = "v2"


class Parcel(BaseModel):
    length_in: float = Field(gt=0)
    width_in: float = Field(gt=0)
    height_in: float = Field(gt=0)
    weight_lb: float = Field(gt=0)


class Destination(BaseModel):
    address1: str
    city: str
    state: str
    postal_code: str
    country: str


class RatesRequest(BaseModel):
    parcel: Parcel
    destination: Destination


class VersionUpdate(BaseModel):
    version: str


# service_code -> (base_cents, cents_per_lb, transit_mode, estimated_days)
SERVICE_TABLE = {
    "GND_ECON": (550, 205, "ground", 7),
    "GND": (795, 142, "ground", 5),
    "AIR_2DAY": (1450, 310, "air", 2),
    "AIR_NEXT": (2600, 380, "air", 1),
    "FREIGHT": (4000, 90, "freight", 6),
}


def quote_services(weight_lb: float) -> list[dict]:
    services = []
    for code, (base_cents, cents_per_lb, transit_mode, days) in SERVICE_TABLE.items():
        price_cents = base_cents + round(cents_per_lb * weight_lb)
        services.append(
            {
                "service_code": code,
                "price_cents": price_cents,
                "transit_mode": transit_mode,
                "estimated_days": days,
            }
        )
    return services


def retired_response(version: str) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "error": f"API version {version} has been retired. "
            f"Current live version is {_live_version}."
        },
    )


@app.post("/v2/rates")
async def rates_v2(body: RatesRequest):
    if _live_version != "v2":
        return retired_response("v2")
    services = quote_services(body.parcel.weight_lb)
    return {"services": services}


@app.post("/v3/rates")
async def rates_v3(body: RatesRequest, x_shipper_id: str | None = Header(default=None)):
    if _live_version != "v3":
        return retired_response("v3")
    if not x_shipper_id:
        raise HTTPException(
            status_code=400,
            detail="X-Shipper-Id header is required for v3 API",
        )
    services = quote_services(body.parcel.weight_lb)
    v3_services = [
        {
            "service_level": s["service_code"],
            "amount": {"value": s["price_cents"], "currency": "USD"},
            "transit_mode": s["transit_mode"],
            "estimated_days": s["estimated_days"],
        }
        for s in services
    ]
    return {"services": v3_services}


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
