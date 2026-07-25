# Self-Healing Integrations — PRD

## Problem
Third-party APIs change their wire format without warning. Integration adapters
break in production. Maintenance is 80-90% of software cost, and a large slice of
it is translation code breaking when a vendor renames a field. The intent never
changed; only the translation did.

## Approach
Adapter intent lives in a versioned PDD prompt with numbered contract rules.
Vendor wire format lives in a pinned OpenAPI snapshot file, included as context.
When the vendor changes, we replace the snapshot and regenerate the adapter from
unchanged intent, then gate the result on the accumulated test suite. The prompt
diff is zero lines; the code diff is the vendor's change absorbed.

## Modules

### src/types/shipping.py
Internal domain types: Parcel, Address, Quote. No vendor concepts. Quote carries
an integer minor-unit amount and a currency.

### integrations/shipfast/adapter.py
get_quote(parcel: Parcel, destination: Address) -> Quote

Translates internal types into a ShipFast rate request, calls the rates endpoint,
translates the response back into Quote.

Contract rules:
- R1 (MUST): Return the cheapest available ground service for the parcel and destination.
- R2 (MUST): Express quoted price in integer minor units of the response currency.
- R3 (MUST): Raise NoServiceAvailable when zero eligible ground services are returned.
- R4 (MUST NOT): Retry a request that failed with a 4xx status other than 429.
- R5 (MUST): Time out after 3 seconds and raise ProviderTimeout.
- R6 (MUST NOT): Log or return the ShipFast API key, account number, or address lines.

Vocabulary:
- Ground service: any ShipFast service whose transit mode is surface or ground,
  excluding air and freight.
- Quoted price: total charged to the customer, integer minor units, inclusive of
  carrier surcharges, exclusive of tax.

Non-responsibilities: does not choose between carriers, does not persist quotes,
does not purchase labels.

### verification/story_gate.py
Runs the user-story regression suite against a regenerated candidate and returns
a pass/fail evidence manifest.

## The vendor change we heal (ShipFast v2 -> v3)
- `price_cents` (integer) becomes a nested `amount` object: {"value": int, "currency": str}
- `service_code` becomes `service_level`
- New required request header: `X-Shipper-Id`

None of these facts appear in the adapter prompt. They live only in the pinned
OpenAPI snapshot, which is what gets replaced.

## Out of scope (hand-written glue, not regenerated)
Mock upstream service, Render task wiring, sponsor SDK calls, CLI output.
