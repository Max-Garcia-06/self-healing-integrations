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

export interface DiffRow {
  tag: "equal" | "insert" | "delete" | "replace";
  leftNo: number | null;
  left: string | null;
  rightNo: number | null;
  right: string | null;
}

export interface FileDiff {
  key: string;
  filename: string;
  lang: string;
  before_label: string;
  after_label: string;
  changed: boolean;
  stat: { added: number; removed: number };
  rows: DiffRow[];
}

export interface Diffs {
  files: FileDiff[];
  prompt: { filename: string; content: string; changed: boolean; note?: string };
}

export interface Source {
  prompt: { filename: string; content: string; note?: string };
  adapter_v2: { filename: string; content: string; label: string; lang: string };
  spec: FileDiff;
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
