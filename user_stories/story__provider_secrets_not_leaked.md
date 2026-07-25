# Provider secrets never leak on error

**Given** our provider credentials (API key and account number) and a
customer's street address
**When** the provider returns an error instead of a quote
**Then** the error we raise says what went wrong
**But** the error message contains no API key and no account number
**And** nothing we log contains the API key or the account number
**And** neither the error message nor anything we log contains any line of
the customer's street address

This holds for every kind of provider error, not just one specific case. If
someone reads only the exception message and the logs, they must not be able
to recover the credentials or find out where the customer lives.
