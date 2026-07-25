# Cheapest ground rate wins

**Given** a 3 lb parcel shipping to Denver, CO 80202
**And** the provider offers three services for this parcel and destination:
  - a ground service at $12.40
  - a ground economy service at $14.10
  - an air service at $9.90
**When** we ask for a shipping quote
**Then** we get back 1240 USD

The air service is cheaper than both ground options, but it is not a ground
service, so it is never a candidate. Only the ground and ground economy
services compete, and the cheaper of those two wins.
