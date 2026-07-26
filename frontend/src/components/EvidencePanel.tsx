import type { DemoEvent, RunState } from "../types";

interface Fact {
  label: string;
  key: "prompt" | "spec" | "adapter" | "business";
  want: string; // the value that means "good"
}

const FACTS: Fact[] = [
  { label: "Durable prompt", key: "prompt", want: "unchanged" },
  { label: "Vendor specification", key: "spec", want: "changed" },
  { label: "Generated adapter", key: "adapter", want: "changed" },
  { label: "Business result", key: "business", want: "preserved" },
];

export function EvidencePanel({
  evidence,
  healed,
  runState,
}: {
  evidence: DemoEvent | undefined;
  healed: DemoEvent | undefined;
  runState: RunState;
}) {
  const details = evidence?.details as Record<string, string> | undefined;
  const ready = Boolean(details);

  return (
    <div className="panel">
      <h2 className="panel-title">Evidence</h2>
      {!ready ? (
        <p className="muted">
          {runState === "failed"
            ? "The heal did not complete, so end-to-end evidence was not produced."
            : "Evidence is verified from the real run once the adapter is regenerated."}
        </p>
      ) : (
        <ul className="evidence">
          {FACTS.map((f) => {
            const value = details?.[f.key] ?? "—";
            const good = value === f.want;
            return (
              <li key={f.key} className={good ? "ev-good" : "ev-bad"}>
                <span className="ev-mark">{good ? "✓" : "✕"}</span>
                <span className="ev-label">{f.label}</span>
                <span className="ev-value">{value}</span>
              </li>
            );
          })}
        </ul>
      )}
      {ready && healed?.details && (
        <p className="ev-foot">
          Same business answer before and after the break:{" "}
          <strong>
            {String(healed.details.amount)} {String(healed.details.currency)}
          </strong>{" "}
          ({String(healed.details.service)}).
        </p>
      )}
    </div>
  );
}
