import type { DemoEvent, StepId, StepStatus } from "../types";
import { TIMELINE } from "../types";

function statusOf(
  events: Record<string, DemoEvent>,
  id: StepId
): StepStatus | "pending" {
  return events[id]?.status ?? "pending";
}

const GLYPH: Record<string, string> = {
  pending: "○",
  running: "◇",
  passed: "✓",
  expected_failure: "⚠",
  failed: "✕",
};

const STATUS_TEXT: Record<string, string> = {
  pending: "pending",
  running: "running",
  passed: "passed",
  expected_failure: "expected break",
  failed: "failed",
};

export function Timeline({
  events,
  terminalStep,
}: {
  events: Record<string, DemoEvent>;
  terminalStep: StepId | null;
}) {
  return (
    <div className="panel">
      <h2 className="panel-title">Workflow</h2>
      <ol className="timeline">
        {TIMELINE.map((step, i) => {
          const status = statusOf(events, step.id);
          const ev = events[step.id];
          return (
            <li key={step.id} className={`tl-item status-${status}`}>
              <div className="tl-rail">
                <span className="tl-glyph">{GLYPH[status]}</span>
                {i < TIMELINE.length - 1 && <span className="tl-line" />}
              </div>
              <div className="tl-body">
                <div className="tl-head">
                  <span className="tl-index">{i + 1}</span>
                  <span className="tl-label">{step.label}</span>
                  <span className={`tl-status status-${status}`}>
                    {STATUS_TEXT[status]}
                  </span>
                </div>
                {ev?.message && <div className="tl-msg">{ev.message}</div>}
              </div>
            </li>
          );
        })}
      </ol>
      {terminalStep === "complete" && (
        <div className="tl-terminal complete">SELF-HEAL COMPLETE</div>
      )}
      {terminalStep === "error" && (
        <div className="tl-terminal failed">RUN HALTED</div>
      )}
    </div>
  );
}
