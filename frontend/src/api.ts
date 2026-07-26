import type { DemoEvent, Diffs, Source } from "./types";

export async function startRun(): Promise<string> {
  const res = await fetch("/api/demo/run", { method: "POST" });
  if (res.status === 409) {
    throw new Error("A demo run is already in progress. Try again in a moment.");
  }
  if (!res.ok) {
    throw new Error(`Backend returned ${res.status} starting the run`);
  }
  const data = (await res.json()) as { run_id: string };
  return data.run_id;
}

export interface EventStream {
  close: () => void;
}

/**
 * Open the SSE stream for a run. Calls onEvent for each DemoEvent, onDisconnect
 * when the browser loses the connection unexpectedly (the UI stays usable).
 * The caller is responsible for closing on a terminal event.
 */
export function openEventStream(
  runId: string,
  onEvent: (ev: DemoEvent) => void,
  onDisconnect: () => void
): EventStream {
  const es = new EventSource(`/api/demo/events/${runId}`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as DemoEvent);
    } catch {
      /* ignore malformed frame */
    }
  };
  es.onerror = () => {
    // EventSource auto-reconnects; surface a soft warning but keep state.
    onDisconnect();
  };
  return { close: () => es.close() };
}

export async function fetchDiffs(runId: string): Promise<Diffs> {
  const res = await fetch(`/api/demo/diffs/${runId}`);
  if (!res.ok) throw new Error(`Backend returned ${res.status} fetching diffs`);
  return (await res.json()) as Diffs;
}

export async function fetchSource(): Promise<Source> {
  const res = await fetch("/api/demo/source");
  if (!res.ok) throw new Error(`Backend returned ${res.status} fetching source`);
  return (await res.json()) as Source;
}
