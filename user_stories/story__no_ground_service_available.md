# No ground service available raises an error

**Given** a parcel and destination where the provider only offers an air
service and a freight service
**When** we ask for a shipping quote
**Then** we get no quote back
**And** an error is raised telling us no service is available for this
parcel and destination

Neither of the two offered services is a ground service, so there is nothing
eligible to quote. This must never be mistaken for "no rates returned at all"
— the provider did respond, just with nothing we're allowed to offer.
