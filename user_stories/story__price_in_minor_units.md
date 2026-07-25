# Price is always a whole number of minor units

**Given** a parcel and destination where the cheapest eligible ground service
costs twelve dollars and forty cents
**When** we ask for a shipping quote
**Then** the price we get back is the whole number 1240, with currency USD
**And** it is never the decimal number 12.40 and never the string "$12.40"

**Given** a parcel and destination where the cheapest eligible ground service
is priced by the provider in euros, nine euros and fifty cents
**When** we ask for a shipping quote
**Then** the price we get back is the whole number 950, with currency EUR

In both cases the price is a plain integer count of minor units (cents), never
a float and never a dollar-and-cents string. A reader should never be able to
find a decimal point anywhere near the price.
