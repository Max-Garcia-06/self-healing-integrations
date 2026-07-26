import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DemoEvent, Diffs, RunState, Source, StepId } from "./types";
import { fetchDiffs, fetchSource, openEventStream, startRun } from "./api";
import type { EventStream } from "./api";
import { Timeline } from "./components/Timeline";
import { ResultDetails } from "./components/ResultDetails";
import { EvidencePanel } from "./components/EvidencePanel";
import { CodeChanges } from "./components/CodeChanges";

export default function App() {
  const [runState, setRunState] = useState<RunState>("idle");
  const [events, setEvents] = useState<Record<string, DemoEvent>>({});
  const [diffs, setDiffs] = useState<Diffs | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const streamRef = useRef<EventStream | null>(null);

  // Load the current code up front so the Code changes panel is never empty.
  useEffect(() => {
    fetchSource().then(setSource).catch(() => undefined);
  }, []);

  const reset = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
    setEvents({});
    setDiffs(null);
    setError(null);
    setDisconnected(false);
    setRunState("idle");
  }, []);

  const onEvent = useCallback((ev: DemoEvent) => {
    setDisconnected(false);
    setEvents((prev) => ({ ...prev, [ev.step]: ev }));
    if (ev.step === "complete") {
      setRunState("complete");
      streamRef.current?.close();
    } else if (ev.step === "error") {
      setRunState("failed");
      if (ev.message) setError(ev.message);
      streamRef.current?.close();
    }
  }, []);

  const run = useCallback(async () => {
    reset();
    setRunState("running");
    try {
      const runId = await startRun();
      streamRef.current = openEventStream(runId, onEvent, () => setDisconnected(true));
      // Fetch diffs once the run settles (poll a couple of times; cheap + honest).
      const poll = setInterval(async () => {
        try {
          const d = await fetchDiffs(runId);
          setDiffs(d);
        } catch {
          /* not ready */
        }
      }, 1500);
      // stop polling after 12 minutes as a hard cap
      setTimeout(() => clearInterval(poll), 12 * 60 * 1000);
    } catch (e) {
      setRunState("failed");
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [onEvent, reset]);

  const statusLabel = useMemo(() => {
    switch (runState) {
      case "idle": return "Idle";
      case "running": return "Running…";
      case "complete": return "Self-heal complete";
      case "failed": return "Halted";
    }
  }, [runState]);

  const healed = events["healed"];
  const evidence = events["evidence"];
  const terminalStep: StepId | null =
    runState === "complete" ? "complete" : runState === "failed" ? "error" : null;

  return (
    <div className="app">
      <header className="header">
        <div className="header-main">
          <h1>Newt</h1>
          <p className="subtitle">
            Durable <span className="accent">intent</span> regenerates disposable
            integrations when a vendor API changes underneath them.
          </p>
        </div>
        <div className={`run-badge state-${runState}`}>
          <span className="dot" />
          {statusLabel}
        </div>
      </header>

      <section className="action">
        <button className="run-btn" onClick={run} disabled={runState === "running"}>
          {runState === "running" ? "Running…" : "Run Healing Demo"}
        </button>
        {(runState === "complete" || runState === "failed") && (
          <button className="reset-btn" onClick={reset}>
            Reset
          </button>
        )}
        {disconnected && runState === "running" && (
          <span className="warn-inline">event stream reconnecting…</span>
        )}
      </section>

      {error && (
        <div className="error-banner">
          <strong>Run halted.</strong> {error}
        </div>
      )}

      <main className="grid">
        <div className="col">
          <Timeline events={events} terminalStep={terminalStep} />
        </div>
        <div className="col">
          <ResultDetails events={events} />
          <EvidencePanel evidence={evidence} healed={healed} runState={runState} />
        </div>
      </main>

      <CodeChanges source={source} diffs={diffs} healed={runState === "complete"} />

      <footer className="foot">
        <span>ShipFast v2 → v3 &middot; PDD-regenerated adapter &middot; live from <code>scripts/demo.sh</code></span>
      </footer>
    </div>
  );
}
