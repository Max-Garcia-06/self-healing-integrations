# CLAUDE.md

## Project Overview

This repository contains a hackathon project tentatively called **IntentBridge**.

IntentBridge monitors third-party API specifications and regenerates integration adapters when an upstream API changes, while preserving the customer’s stable business intent.

The central idea is:

> Business intent is durable. Vendor wire formats are replaceable. Integration adapters should be regenerated rather than repeatedly patched.

This project is being built for the Prompt-Driven Development Hackathon and must visibly demonstrate PDD principles:

* Prompts define behavior.
* Generated code is not the primary source of truth.
* Behavioral changes are made by editing prompts or replaceable context and regenerating.
* Intent remains explicit in prompts and human-authored stories.
* Generated implementation code is reviewed and verified, but treated as disposable.

## Core Demo Scenario

The controlled demo integration is a fictional shipping API named **ShipFast**.

ShipFast starts on API v2.

### ShipFast v2

Request:

```json
{
  "weight_oz": 48,
  "destination_zip": "95112"
}
```

Response:

```json
{
  "rates": [
    {
      "service_code": "GROUND_STANDARD",
      "price_cents": 1240,
      "currency": "USD"
    },
    {
      "service_code": "GROUND_PRIORITY",
      "price_cents": 1680,
      "currency": "USD"
    },
    {
      "service_code": "AIR_EXPRESS",
      "price_cents": 990,
      "currency": "USD"
    }
  ]
}
```

ShipFast then releases API v3.

### ShipFast v3

Changes include:

* `price_cents` becomes `amount.value`.
* `service_code` becomes a nested `service_level` object.
* The request body becomes nested.
* `X-Shipper-Id` becomes a required header.

Request:

```json
{
  "parcel": {
    "weight": {
      "value": 48,
      "unit": "oz"
    }
  },
  "destination": {
    "postal_code": "95112"
  }
}
```

Response:

```json
{
  "rates": [
    {
      "service_level": {
        "code": "GROUND_STANDARD",
        "name": "Ground Standard",
        "transit_mode": "ground"
      },
      "amount": {
        "value": 1240,
        "currency": "USD"
      }
    },
    {
      "service_level": {
        "code": "GROUND_PRIORITY",
        "name": "Ground Priority",
        "transit_mode": "ground"
      },
      "amount": {
        "value": 1680,
        "currency": "USD"
      }
    },
    {
      "service_level": {
        "code": "AIR_EXPRESS",
        "name": "Air Express",
        "transit_mode": "air"
      },
      "amount": {
        "value": 990,
        "currency": "USD"
      }
    }
  ]
}
```

The stable business requirement remains unchanged:

> Return the cheapest eligible ground service, even if an air service is cheaper.

The correct result remains equivalent to:

```json
{
  "serviceName": "Ground Standard",
  "priceMinorUnits": 1240,
  "currency": "USD"
}
```

The demo must show:

1. The generated v2 adapter works against ShipFast v2.
2. ShipFast is switched to v3.
3. The old adapter becomes incompatible.
4. The new OpenAPI specification replaces the pinned snapshot.
5. PDD regenerates the adapter.
6. The same durable business stories pass.
7. The prompt has zero changed lines.
8. The API specification and generated adapter have meaningful diffs.

## Product Scope

The architecture should be provider-agnostic, but the hackathon implementation only needs one complete end-to-end integration.

ShipFast is a controlled demonstration integration, not a hardcoded product boundary.

The generic product flow is:

```text
Fetch provider specification
        ↓
Compare with pinned snapshot
        ↓
Classify the change
        ↓
Create isolated repository workspace
        ↓
Replace the specification snapshot
        ↓
Run PDD regeneration
        ↓
Run tests and behavioral verification
        ↓
Produce evidence and diffs
        ↓
Approve or escalate
```

Do not claim that the system can safely repair every possible API change.

The intended boundary is:

* Mechanical schema changes may be regenerated automatically.
* Additive nonbreaking changes may require no action.
* Semantic changes must be escalated.
* Major protocol or architectural migrations require human intervention.

Examples of semantic changes that must be escalated:

* Prices previously included surcharges but now exclude them.
* A formerly idempotent operation is no longer idempotent.
* Authentication changes from API keys to user OAuth.
* A synchronous endpoint becomes webhook-only.
* The provider removes a capability required by the business contract.

## System Architecture

Treat this as a conventional full-stack application with one specialized background regeneration pipeline.

```text
React dashboard
      ↓
Control-plane API
      ↓
Render Workflow
      ↓
Temporary isolated repository workspace
      ↓
PDD regeneration and verification
      ↓
Structured result shown in dashboard
```

Expected high-level components:

```text
apps/web
    React dashboard

apps/api
    Control-plane API

apps/shipfast-mock
    Controlled third-party provider simulation

workflows
    Render Workflow orchestration

packages/contracts
    Shared TypeScript interfaces

regeneration-target
    PDD-managed demonstration integration

scripts
    Local regeneration and verification commands
```

The exact repository structure may differ. Inspect the repository before assuming files or packages exist.

## External Product Versus Target Repository

In a production deployment, IntentBridge would exist outside the customer’s main codebase.

The external platform would:

* monitor API providers,
* clone authorized repositories,
* create isolated branches or worktrees,
* update API specification snapshots,
* run PDD,
* run tests,
* calculate diffs,
* and propose changes through a pull request.

The customer repository would contain:

* durable intent prompts,
* API specification snapshots,
* generated adapters,
* human-authored stories,
* relevant tests,
* PDD configuration.

For the hackathon, these concerns may live in one monorepo for simplicity, but they should remain conceptually separated.

## PDD Source-of-Truth Rules

For the ShipFast adapter, the sources of truth are:

1. The stable adapter prompt.
2. Human-authored business stories and contract rules.
3. The pinned ShipFast OpenAPI snapshot.
4. Stable internal application interfaces.

The generated adapter is not the source of truth.

The prompt should contain stable business behavior such as:

* Return the cheapest eligible ground service.
* Express prices in integer minor units.
* Raise a known error when no eligible ground service exists.
* Do not retry normal 4xx responses.
* Time out after a defined duration.
* Never expose secrets or customer address lines in logs.

The prompt should not contain unstable vendor-schema details such as:

* `price_cents`
* `service_code`
* `amount.value`
* `service_level`
* `X-Shipper-Id`

Those details belong in the replaceable OpenAPI snapshot.

Conceptually:

```text
Prompt:
What the business wants

OpenAPI snapshot:
How the provider currently works

Generated adapter:
Translation between the two
```

## Generated-Code Policy

Do not manually patch PDD-generated adapter code as the first response to a problem.

When generated behavior is wrong:

1. Identify whether the prompt, context, contract, or story is incomplete.
2. Modify the appropriate authoritative artifact.
3. Run PDD again.
4. Review the generated diff.
5. Run verification.

Avoid:

```text
Edit generated adapter directly
        ↓
Prompt remains incomplete
        ↓
Next PDD sync removes the fix
```

Prefer:

```text
Clarify prompt, context, or story
        ↓
Regenerate adapter
        ↓
Future generations preserve the behavior
```

If an urgent manual generated-code edit is unavoidable, it must later be synchronized back into the authoritative prompt or context.

## PDD-Managed Versus Handwritten Code

### PDD-managed development unit

Treat the following files as one logical unit:

```text
Adapter prompt
Provider specification snapshot
Generated adapter
Generated schema-aware tests
User-story links
PDD metadata
```

One person should own the entire development unit to avoid conflicts and accidental overwrites.

### Handwritten application code

The following may use normal development practices:

* React components
* Express or Fastify routes
* Render Workflow definitions
* Mock ShipFast API
* Database or in-memory repositories
* Diff display
* Deployment configuration
* GitHub integration
* CSS and visual polish

Not every file must be generated through PDD.

The project must clearly demonstrate PDD on the integration adapter where prompt-driven regeneration provides real value.

## Shared Contracts

Prefer shared interfaces that isolate the platform from the regeneration implementation.

A generic integration configuration should resemble:

```typescript
export interface IntegrationDefinition {
  id: string;
  name: string;

  specSource: {
    type: "openapi-url" | "local-file";
    location: string;
  };

  promptPath: string;
  snapshotPath: string;
  generatedPaths: string[];
  syncTarget: string;
  testCommand: string;
}
```

A workflow result should resemble:

```typescript
export type RunStatus =
  | "queued"
  | "probing"
  | "change_detected"
  | "regenerating"
  | "verifying"
  | "awaiting_review"
  | "verified"
  | "escalated"
  | "failed";

export interface DiffSummary {
  changedFiles: string[];
  additions: number;
  deletions: number;
  patch?: string;
}

export interface TestSummary {
  passed: number;
  failed: number;
  durationMs: number;
}

export interface WorkflowEvent {
  step: string;
  status: "pending" | "running" | "passed" | "failed";
  message: string;
  timestamp: string;
}

export interface HealResult {
  runId: string;
  integrationId: string;
  status: RunStatus;

  classification:
    | "unchanged"
    | "non_breaking"
    | "breaking"
    | "semantic_change";

  promptDiff: DiffSummary;
  specDiff: DiffSummary;
  adapterDiff: DiffSummary;

  tests: TestSummary;
  events: WorkflowEvent[];

  escalationReason?: string;
}
```

Do not duplicate similar contracts across packages. Prefer one shared definition.

## Current Workstream Ownership

Unless explicitly told otherwise, assume this Claude Code session is primarily working on the **platform and full-stack product shell**.

Likely owned areas:

```text
apps/web
apps/api
apps/shipfast-mock
workflows
packages/contracts
deployment configuration
```

The teammate’s likely owned areas are:

```text
regeneration-target
PDD prompts
OpenAPI snapshots
generated adapter
business stories
adapter tests
regeneration script
```

Avoid modifying teammate-owned PDD files unless the user explicitly requests it.

Coordinate through stable shared contracts rather than reaching across ownership boundaries.

## Mock ShipFast API Requirements

The mock API must be deterministic and controllable.

Required endpoints:

```http
GET  /health
GET  /openapi.json
GET  /admin/version
POST /admin/version
POST /rates
```

`GET /openapi.json` must return the OpenAPI document for the currently active version.

`POST /admin/version` should accept:

```json
{
  "version": "v3"
}
```

The old v2 adapter must visibly fail against v3.

Possible v3 failure response:

```json
{
  "error": "MISSING_REQUIRED_HEADER",
  "message": "X-Shipper-Id is required in API v3"
}
```

or:

```json
{
  "error": "INVALID_REQUEST_SCHEMA",
  "message": "parcel.weight and destination.postal_code are required"
}
```

The desired demonstration is:

```text
v2 adapter + v2 API → works

v2 adapter + v3 API → fails

regenerated v3 adapter + v3 API → works
```

## Workflow Requirements

The minimum Render Workflow should include:

```text
probe
  ↓
regenerate
  ↓
verify
  ↓
publish result
```

A richer version may include:

```text
probe
  ↓
mechanical and semantic diff
  ↓
regenerate
  ↓
verify
  ↓
review
  ↓
open pull request
```

The workflow should be configuration-driven rather than hardcoded around ShipFast.

Avoid:

```typescript
healShipFast();
```

Prefer:

```typescript
healIntegration(integrationDefinition);
```

The ShipFast-specific information should live in configuration, its prompt, its OpenAPI snapshot, and its stories.

## Regeneration Isolation

PDD regeneration should occur in an isolated workspace.

Conceptual process:

```text
Create temporary directory
        ↓
Copy or clone target repository
        ↓
Create candidate branch or worktree
        ↓
Replace only the configured API snapshot
        ↓
Run PDD sync
        ↓
Run tests
        ↓
Calculate diffs
        ↓
Return structured result
        ↓
Discard or publish candidate
```

Do not directly mutate the production branch or active working tree during automated regeneration.

For the hackathon, a temporary directory is acceptable.

A production implementation would use stronger isolation such as ephemeral containers or Git worktrees.

## Verification Requirements

A successful PDD command is not sufficient evidence.

Verification should include:

1. Expected output file exists.
2. Generated module compiles or imports.
3. Unit tests pass.
4. Human-authored business stories pass.
5. No unexpected files changed.
6. No tests or contracts were silently removed.
7. Stable public interfaces remain compatible.
8. No credentials or private data appear in output.

Expected evidence:

```json
{
  "generation": "passed",
  "compile": "passed",
  "tests": {
    "passed": 12,
    "failed": 0
  },
  "stories": {
    "passed": 3,
    "failed": 0
  },
  "unexpectedChanges": []
}
```

## Dashboard Requirements

The dashboard only needs to communicate the core story clearly.

Required views:

### Integration list

Example:

```text
ShipFast       Breaking change     Regenerating
TaxCloud       Healthy             Idle
InventoryHub   Healthy             Idle
```

Only ShipFast needs a complete implementation.

### Workflow timeline

Example:

```text
✓ Provider probed
✓ Schema change detected
✓ Adapter regenerated
✓ Tests passed
○ Awaiting review
```

### Diff evidence

The most important presentation is:

```text
Prompt diff:   0 changed lines
Spec diff:     provider schema changed
Adapter diff:  generated implementation changed
Tests:         passing
```

Visual clarity is more important than adding many screens.

## Priorities

Implement in this order:

1. Working ShipFast v2 mock.
2. Working generated v2 adapter.
3. Reliable switch to ShipFast v3.
4. Old adapter visibly fails.
5. Local PDD regeneration succeeds.
6. Stable stories pass after regeneration.
7. Structured `HealResult` is produced.
8. Render Workflow runs the pipeline.
9. Dashboard displays progress and evidence.
10. Deployment works.
11. Add sponsor integrations only after the full spine is reliable.

Optional additions, in priority order:

1. MiniMax semantic-change explanation.
2. Band audit or reviewer room.
3. GitHub pull-request creation.
4. Multiple fake integrations.
5. ElevenLabs voice notification.

Do not let optional sponsor integrations break the core demo.

## Definition of Done

The MVP is complete when:

```text
[ ] ShipFast v2 API is active.
[ ] Generated v2 adapter returns the cheapest ground rate.
[ ] ShipFast can be switched to v3 through an endpoint or dashboard button.
[ ] The old v2 adapter fails against v3.
[ ] The workflow fetches the v3 OpenAPI specification.
[ ] The pinned API snapshot is replaced.
[ ] PDD regenerates the adapter.
[ ] The stable business stories pass.
[ ] The intent prompt has zero changed lines.
[ ] The specification and adapter have visible diffs.
[ ] The process runs through Render Workflows.
[ ] The deployed dashboard displays the result.
[ ] A backup demo recording exists.
```

Do not continue adding scope once these conditions are satisfied unless the user explicitly requests it.

## Git and Collaboration Rules

Use ordinary Git collaboration alongside PDD.

Git manages:

* branches,
* commits,
* pulls,
* merges,
* PRs,
* teammate collaboration.

PDD manages:

* authoritative intent,
* prompt-to-code generation,
* regeneration,
* synchronization,
* prompt and code traceability.

Use feature branches rather than both teammates pushing directly to `main`.

Suggested branches:

```text
feature/platform-shell
feature/pdd-regeneration
feature/render-workflow
```

Keep commits small enough to review but complete enough to leave the project runnable.

A PDD regeneration should generally be one atomic logical commit containing:

* updated specification snapshot,
* regenerated adapter,
* regenerated schema-aware tests,
* relevant PDD metadata,
* verification results when appropriate.

Example commit:

```text
feat: regenerate ShipFast adapter for API v3

- update pinned ShipFast OpenAPI snapshot
- regenerate adapter from unchanged business intent
- regenerate schema-aware tests
- verify durable shipping stories
```

Do not commit incomplete PDD states where the snapshot, generated implementation, and verification disagree.

## Claude Code Working Style

Before changing code:

1. Inspect the repository structure.
2. Identify package manager and workspace configuration.
3. Read existing contracts and scripts.
4. Determine whether the target file is handwritten or PDD-managed.
5. Check the current Git branch and working-tree state.
6. Avoid overwriting teammate work.

When implementing:

* Prefer the smallest change that advances the end-to-end demo.
* Reuse existing patterns and dependencies.
* Avoid unnecessary abstractions.
* Avoid speculative production infrastructure.
* Keep provider-specific behavior out of the generic workflow.
* Add validation and useful errors around external inputs.
* Keep all demo behavior deterministic.
* Do not fabricate successful workflow, PDD, test, or deployment results.
* Run relevant checks before reporting completion.
* State clearly what was verified and what remains unverified.

When the user gives a broad task, propose and execute a reasonable implementation rather than repeatedly asking for minor clarification.

## Commands

Inspect the repository and update this section when the real commands are known.

Expected categories:

```bash
# Install dependencies
npm install

# Start all local services
npm run dev

# Start dashboard
npm run dev:web

# Start control-plane API
npm run dev:api

# Start mock ShipFast
npm run dev:shipfast

# Run tests
npm test

# Run ShipFast regeneration
npm run regenerate -- shipfast

# Run PDD directly from the regeneration target
pdd --force sync shipfast_adapter

# Build
npm run build
```

Do not assume these scripts exist. Check `package.json` files before invoking or editing them.

## Final Product Statement

Use this description when reasoning about scope:

> IntentBridge is a provider-agnostic regeneration and verification platform for contract-driven API adapters. Customers register a specification source, durable PDD intent prompt, generated module, and verification command. IntentBridge detects provider changes, regenerates mechanical translations when stable business contracts can still be proven, and escalates semantic changes that require a human decision.

The hackathon proves this architecture through one deeply implemented ShipFast integration.
