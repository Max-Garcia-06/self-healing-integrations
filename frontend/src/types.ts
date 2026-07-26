// Mirrors the events the backend derives from scripts/demo.sh.

export type StepId =
  | "starting_mock"
  | "baseline"
  | "provider_change"
  | "expected_failure"
  | "regeneration"
  | "healed"
  | "evidence"
  | "complete"
  | "error";

export type StepStatus =
  | "pending"
  | "running"
  | "passed"
  | "expected_failure"
  | "failed";

export interface DemoEvent {
  step: StepId;
  status: StepStatus;
  title: string;
  message?: string;
  details?: Record<string, unknown>;
  timestamp: string;
}

export interface Diffs {
  spec_diff: string;
  adapter_diff: string;
  spec_stat: { added: number; removed: number };
  adapter_stat: { added: number; removed: number };
}

// The seven visible workflow steps, in order.
export const TIMELINE: { id: StepId; label: string }[] = [
  { id: "starting_mock", label: "Baseline provider" },
  { id: "baseline", label: "Baseline adapter" },
  { id: "provider_change", label: "Vendor API change" },
  { id: "expected_failure", label: "Integration breaks" },
  { id: "regeneration", label: "PDD regeneration" },
  { id: "healed", label: "Integration healed" },
  { id: "evidence", label: "Evidence verified" },
];

export type RunState = "idle" | "running" | "complete" | "failed";
