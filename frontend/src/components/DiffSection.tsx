import { useState } from "react";
import type { Diffs } from "../types";

function DiffBlock({
  title,
  diff,
  stat,
  note,
}: {
  title: string;
  diff: string;
  stat: { added: number; removed: number };
  note?: string;
}) {
  const [open, setOpen] = useState(false);
  const empty = stat.added === 0 && stat.removed === 0;
  return (
    <div className="diff-block">
      <button className="diff-head" onClick={() => setOpen((o) => !o)}>
        <span className="diff-caret">{open ? "▾" : "▸"}</span>
        <span className="diff-title">{title}</span>
        <span className="diff-stat">
          <span className="added">+{stat.added}</span>{" "}
          <span className="removed">−{stat.removed}</span>
        </span>
      </button>
      {note && empty && <div className="diff-note">{note}</div>}
      {open && (
        <pre className="diff-body">
          {diff.split("\n").map((line, i) => {
            let cls = "d-ctx";
            if (line.startsWith("+") && !line.startsWith("+++")) cls = "d-add";
            else if (line.startsWith("-") && !line.startsWith("---")) cls = "d-del";
            else if (line.startsWith("@@")) cls = "d-hunk";
            else if (line.startsWith("+++") || line.startsWith("---")) cls = "d-file";
            return (
              <div key={i} className={cls}>
                {line || " "}
              </div>
            );
          })}
        </pre>
      )}
    </div>
  );
}

export function DiffSection({ diffs }: { diffs: Diffs | null }) {
  if (!diffs) return null;
  return (
    <section className="panel diff-section">
      <h2 className="panel-title">Diffs</h2>
      <DiffBlock
        title="OpenAPI specification (v2 → v3)"
        diff={diffs.spec_diff}
        stat={diffs.spec_stat}
      />
      <DiffBlock
        title="Generated adapter (v2 baseline → healed v3)"
        diff={diffs.adapter_diff}
        stat={diffs.adapter_stat}
        note="No change yet — the adapter is regenerated only when PDD healing completes."
      />
    </section>
  );
}
