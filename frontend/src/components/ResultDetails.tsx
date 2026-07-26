import type { DemoEvent } from "../types";

function num(v: unknown): string {
  return typeof v === "number" ? v.toLocaleString() : String(v ?? "—");
}
function str(v: unknown): string {
  return v === undefined || v === null ? "—" : String(v);
}

export function ResultDetails({ events }: { events: Record<string, DemoEvent> }) {
  const baseline = events["baseline"]?.details;
  const change = events["provider_change"]?.details;
  const fail = events["expected_failure"]?.details;
  const regen = events["regeneration"];
  const healed = events["healed"]?.details;

  const rows: { label: string; value: React.ReactNode; tone?: string }[] = [];

  if (baseline) {
    rows.push({ label: "Baseline (v2)", value: `${str(baseline.service)} — ${num(baseline.amount)} ${str(baseline.currency)}`, tone: "ok" });
  }
  if (change) {
    rows.push({ label: "Provider", value: `${str(change.from)} → ${str(change.to)}`, tone: "shift" });
  }
  if (fail) {
    const status = fail.http_status ? `HTTP ${num(fail.http_status)}` : "";
    rows.push({
      label: "Stale adapter",
      value: `${str(fail.exception ?? "failed")} ${status}`.trim(),
      tone: "expected",
    });
  }
  if (regen) {
    const dur = regen.details?.duration_seconds;
    const val =
      regen.status === "passed"
        ? `regenerated${typeof dur === "number" ? ` in ${dur}s` : ""}`
        : regen.status === "running"
        ? "running…"
        : "failed";
    rows.push({ label: "PDD regeneration", value: val, tone: regen.status === "failed" ? "bad" : regen.status === "passed" ? "ok" : "shift" });
  }
  if (healed) {
    rows.push({ label: "Healed (v3)", value: `${str(healed.service)} — ${num(healed.amount)} ${str(healed.currency)}`, tone: "ok" });
  }

  return (
    <div className="panel">
      <h2 className="panel-title">Result details</h2>
      {rows.length === 0 ? (
        <p className="muted">Run the demo to populate live results from the real adapter.</p>
      ) : (
        <dl className="kv">
          {rows.map((r, i) => (
            <div key={i} className="kv-row">
              <dt>{r.label}</dt>
              <dd className={`tone-${r.tone ?? "neutral"}`}>{r.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
