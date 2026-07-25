"""Run the PRESERVED v2 adapter against whatever version the vendor is serving.

This is the control case. demo/adapter_v2_stale.py is a byte-for-byte copy of
the adapter PDD generated against the v2 snapshot. Nothing regenerated it.
Point it at a v3 vendor and it breaks — which is the ordinary outcome the rest
of the industry lives with.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.types.shipping import Address, NoServiceAvailable, Parcel, ProviderTimeout

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pin the preserved v2 CONFIG in place first, then load the v2 adapter against
# it, so the failure below is caused by the vendor's change and nothing else.
_load("src.config.shipfast", ROOT / "demo" / "shipfast_config_v2.py")
stale = _load("stale_v2_adapter", ROOT / "demo" / "adapter_v2_stale.py")

parcel = Parcel(weight_grams=1361, length_mm=300, width_mm=200, height_mm=150)
dest = Address(
    line1="1701 Wynkoop St", line2="Suite 200", city="Denver",
    state_or_province="CO", postal_code="80202", country_code="US",
)

try:
    q = stale.get_quote(parcel, dest)
    print(f"stale v2 adapter returned {q.amount_minor_units} {q.currency}")
    sys.exit(0)
except (NoServiceAvailable, ProviderTimeout) as e:
    print(f"BROKEN  {type(e).__name__}: {e}")
    sys.exit(1)
except Exception as e:
    msg = str(e).splitlines()[0]
    print(f"BROKEN  {type(e).__name__}: {msg}")
    sys.exit(1)
