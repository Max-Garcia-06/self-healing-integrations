"""Backend API for the Self-Healing Integrations dashboard.

This is a thin visualization layer. It does NOT reimplement the demo, the
adapter, or the healing logic. It runs the existing, unmodified
`scripts/demo.sh` as a subprocess and translates that script's normal terminal
output into structured events streamed to the browser over Server-Sent Events.

Endpoints:
  POST /api/demo/run              -> {"run_id": ...}   (one run at a time)
  GET  /api/demo/events/{run_id}  -> text/event-stream of DemoEvent JSON
  GET  /api/demo/diffs/{run_id}   -> {spec_diff, adapter_diff, ...}
  GET  /api/health                -> liveness

Reliability:
  * Only one run at a time (409 otherwise).
  * The subprocess runs in its own session; on timeout/shutdown we signal the
    whole group so demo.sh's own cleanup trap restores the mock to v2 and stops
    it. We never leave the mock stuck on v3 or a subprocess running.
  * Real outcomes only — failures (including the honest "PDD regeneration
    failed" case) are surfaced, never faked.
"""
from __future__ import annotations

import asyncio
import contextlib
import difflib
import json
import os
import re
import signal
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

REPO = Path(__file__).resolve().parent.parent
DEMO_SCRIPT = REPO / "scripts" / "demo.sh"
BASELINE_TAG = "shipfast-v2-baseline"
SPEC_V2 = REPO / "context" / "specs" / "shipfast" / "openapi.snapshot.json"
SPEC_V3 = REPO / "context" / "specs" / "shipfast" / "v3.json"
ADAPTER = REPO / "integrations" / "shipfast" / "adapter.py"
ADAPTER_REL = "integrations/shipfast/adapter.py"
ADAPTER_PROMPT = REPO / "integrations" / "shipfast" / "adapter_python.prompt"
RUN_TIMEOUT_SECONDS = 600

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_AMOUNT = re.compile(r"^(\d+)\s+([A-Z]{3})$")

app = FastAPI(title="Self-Healing Integrations — Demo API")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Run:
    def __init__(self, run_id: str, proc: asyncio.subprocess.Process):
        self.id = run_id
        self.proc = proc
        self.events: list[dict[str, Any]] = []
        self.done = False
        self.returncode: int | None = None


_current: Run | None = None
_start_lock = asyncio.Lock()


# --------------------------------------------------------------------------- #
# Output parser: demo.sh terminal lines -> structured DemoEvents
# --------------------------------------------------------------------------- #
class DemoParser:
    """Translate demo.sh's stable terminal markers into DemoEvents.

    Depends only on the script's step banners ("STEP N"), check/cross marks,
    and the handful of fixed result lines it prints. Unrecognized lines (e.g.
    verbose PDD logs) are ignored.
    """

    STEP_BY_NUM = {
        "1": ("starting_mock", "Baseline provider", "Starting ShipFast mock on v2"),
        "2": ("baseline", "Baseline adapter", "Running generated v2 adapter"),
        "3": ("provider_change", "Vendor API change", "Switching provider to v3"),
        "4": ("expected_failure", "Integration breaks", "Running stale adapter against v3"),
        "5": ("regeneration", "PDD regeneration", "Regenerating adapter from the durable prompt via PDD"),
        "6": ("healed", "Integration healed", "Running the regenerated adapter against v3"),
        "7": ("evidence", "Evidence verified", "Checking that durable intent was preserved"),
    }
    TITLES = {step: title for step, title, _ in STEP_BY_NUM.values()}

    def __init__(self, run: Run):
        self.run = run
        self.cur: str | None = None
        self.pending_pass: str | None = None  # step awaiting its amount line
        self.pending_service: str | None = None
        self.ef_active = False
        self.ef_reason: list[str] = []
        self.evidence: dict[str, str] = {}
        self.complete_emitted = False
        self.error_emitted = False

    def _emit(self, step, status, title=None, message=None, details=None):
        ev = {
            "step": step,
            "status": status,
            "title": title or self.TITLES.get(step, step),
            "timestamp": _now(),
        }
        if message:
            ev["message"] = message
        if details:
            ev["details"] = details
        self.run.events.append(ev)

    def feed(self, raw_line: str):
        line = _ANSI.sub("", raw_line).rstrip("\n").rstrip()
        if not line:
            return

        m = re.match(r"^STEP (\d)\b", line)
        if m:
            self._flush_expected_failure()
            num = m.group(1)
            if num in self.STEP_BY_NUM:
                step, title, msg = self.STEP_BY_NUM[num]
                self.cur = step
                self._emit(step, "running", title, msg)
            return

        if line.startswith("SELF-HEAL COMPLETE"):
            self._emit("complete", "passed", "Self-heal complete",
                       "Integration healed and business behavior verified")
            self.complete_emitted = True
            return

        if line.startswith("✗ "):
            msg = line[2:].strip()
            if self.cur:
                self._emit(self.cur, "failed", self.TITLES.get(self.cur), msg)
            return

        # Expected-failure reason lines are buffered until the next STEP banner.
        if self.ef_active:
            if line != "Reason:":
                self.ef_reason.append(line)
            # keep buffering; flush happens on next STEP or at finish()

        if line.startswith("✓ "):
            self._handle_ok(line[2:].strip())
            return

        # amount line, e.g. "1240 USD"
        am = _AMOUNT.match(line)
        if am and self.pending_pass:
            step = self.pending_pass
            self.pending_pass = None
            provider = "v2" if step == "baseline" else "v3"
            self._emit(step, "passed", self.TITLES.get(step),
                       "Cheapest ground service selected",
                       {"provider": provider,
                        "service": self.pending_service or "Ground Standard",
                        "amount": int(am.group(1)), "currency": am.group(2)})
            self.pending_service = None
            return

        # service name line right after a "✓ PASS"
        if self.pending_pass and not am and line not in ("Reason:",):
            self.pending_service = line
            return

        # evidence lines look like "unchanged" / "changed" / "preserved" following
        # a label printed just before; we capture them positionally below.
        self._maybe_capture_evidence(line)

    def _handle_ok(self, what: str):
        if what.startswith("running") and self.cur == "starting_mock":
            self._emit("starting_mock", "passed", self.TITLES["starting_mock"],
                       "ShipFast mock running on v2", {"provider": "v2"})
        elif what.startswith("PASS") and self.cur in ("baseline", "healed"):
            self.pending_pass = self.cur
            self.pending_service = None
        elif what.startswith("provider updated"):
            self._emit("provider_change", "passed", self.TITLES["provider_change"],
                       "Provider now serving the v3 contract", {"from": "v2", "to": "v3"})
        elif what.startswith("EXPECTED FAILURE"):
            self.ef_active = True
            self.ef_reason = []
        elif what.startswith("regenerated"):
            self._emit("regeneration", "passed", self.TITLES["regeneration"],
                       "Adapter regenerated from the v3 spec")
        elif what in ("unchanged", "changed", "preserved", "broken"):
            self._record_evidence(what)

    # ---- evidence (STEP 7) ------------------------------------------------- #
    # The script prints a label line ("Prompt intent:", "Vendor specification:",
    # "Generated adapter:", "Business rule:") then a "✓ <value>" line.
    _EVIDENCE_LABELS = {
        "Prompt intent:": "prompt",
        "Vendor specification:": "spec",
        "Generated adapter:": "adapter",
        "Business rule:": "business",
    }

    def _maybe_capture_evidence(self, line: str):
        if line in self._EVIDENCE_LABELS:
            self._ev_label = self._EVIDENCE_LABELS[line]

    def _record_evidence(self, value: str):
        label = getattr(self, "_ev_label", None)
        if label:
            self.evidence[label] = value
            self._ev_label = None
        # once all four gathered, emit the evidence event
        if len(self.evidence) == 4:
            ok = (self.evidence.get("prompt") == "unchanged"
                  and self.evidence.get("spec") == "changed"
                  and self.evidence.get("adapter") == "changed"
                  and self.evidence.get("business") == "preserved")
            self._emit("evidence", "passed" if ok else "failed",
                       self.TITLES["evidence"],
                       "Durable intent preserved across the vendor change",
                       dict(self.evidence))

    def _flush_expected_failure(self):
        if not self.ef_active:
            return
        self.ef_active = False
        detail = " ".join(self.ef_reason).strip() or "Stale adapter failed as expected"
        details: dict[str, Any] = {"detail": detail}
        if "410" in detail:
            details["http_status"] = 410
            details["exception"] = "NoServiceAvailable"
        self._emit("expected_failure", "expected_failure", self.TITLES["expected_failure"],
                   "Stale adapter rejected by the vendor", details)

    def finish(self, rc: int):
        self._flush_expected_failure()
        if rc == 0:
            if not self.complete_emitted:
                self._emit("complete", "passed", "Self-heal complete",
                           "Integration healed and business behavior verified")
        else:
            self._emit("error", "failed", "Demo did not complete",
                       f"demo.sh exited with code {rc}"
                       + (" (PDD regeneration typically needs `pdd auth login` or a model API key)"
                          if self.cur == "regeneration" else ""))


# --------------------------------------------------------------------------- #
# Subprocess lifecycle
# --------------------------------------------------------------------------- #
async def _pump(run: Run):
    parser = DemoParser(run)
    try:
        assert run.proc.stdout is not None
        async for raw in run.proc.stdout:
            parser.feed(raw.decode(errors="replace"))
    except Exception:
        pass
    finally:
        rc = await run.proc.wait()
        run.returncode = rc
        parser.finish(rc)
        run.done = True


async def _watchdog(run: Run):
    try:
        await asyncio.wait_for(run.proc.wait(), timeout=RUN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        _terminate(run)
        run.events.append({
            "step": "error", "status": "failed", "title": "Timed out",
            "message": f"Demo exceeded {RUN_TIMEOUT_SECONDS}s and was stopped",
            "timestamp": _now(),
        })


def _terminate(run: Run):
    if run.proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(run.proc.pid), signal.SIGTERM)


@app.post("/api/demo/run")
async def run_demo():
    global _current
    async with _start_lock:
        if _current is not None and not _current.done:
            raise HTTPException(status_code=409, detail="A demo run is already in progress")
        if not DEMO_SCRIPT.exists():
            raise HTTPException(status_code=500, detail=f"demo script not found at {DEMO_SCRIPT}")

        env = dict(os.environ)
        env["NO_COLOR"] = "1"
        # Ensure uv / pdd (installed under ~/.local/bin) are resolvable.
        local_bin = str(Path.home() / ".local" / "bin")
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")

        proc = await asyncio.create_subprocess_exec(
            "bash", str(DEMO_SCRIPT),
            cwd=str(REPO), env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        run = Run(uuid.uuid4().hex[:12], proc)
        _current = run
        asyncio.create_task(_pump(run))
        asyncio.create_task(_watchdog(run))
        return {"run_id": run.id}


@app.get("/api/demo/events/{run_id}")
async def events(run_id: str):
    run = _current
    if run is None or run.id != run_id:
        raise HTTPException(status_code=404, detail="Unknown run id")

    async def gen():
        idx = 0
        ticks = 0
        yield ": connected\n\n"
        while True:
            while idx < len(run.events):
                yield f"data: {json.dumps(run.events[idx])}\n\n"
                idx += 1
            if run.done and idx >= len(run.events):
                break
            await asyncio.sleep(0.15)
            ticks += 1
            if ticks % 100 == 0:  # ~15s heartbeat keeps proxies from closing
                yield ": ping\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"},
    )


def _split_rows(before: str, after: str) -> list[dict[str, Any]]:
    """GitHub-style side-by-side rows aligning `before` (left) and `after` (right)."""
    a = before.splitlines()
    b = after.splitlines()
    rows: list[dict[str, Any]] = []
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({"tag": "equal",
                             "leftNo": i1 + k + 1, "left": a[i1 + k],
                             "rightNo": j1 + k + 1, "right": b[j1 + k]})
        elif tag == "delete":
            for k in range(i1, i2):
                rows.append({"tag": "delete", "leftNo": k + 1, "left": a[k],
                             "rightNo": None, "right": None})
        elif tag == "insert":
            for k in range(j1, j2):
                rows.append({"tag": "insert", "leftNo": None, "left": None,
                             "rightNo": k + 1, "right": b[k]})
        else:  # replace — pair lines positionally, spill extras as add/del
            lefts = list(range(i1, i2))
            rights = list(range(j1, j2))
            for k in range(max(len(lefts), len(rights))):
                li = lefts[k] if k < len(lefts) else None
                rj = rights[k] if k < len(rights) else None
                rows.append({
                    "tag": "replace",
                    "leftNo": (li + 1) if li is not None else None,
                    "left": a[li] if li is not None else None,
                    "rightNo": (rj + 1) if rj is not None else None,
                    "right": b[rj] if rj is not None else None,
                })
    return rows


def _stat_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    added = sum(1 for r in rows if r["tag"] in ("insert", "replace") and r["right"] is not None)
    removed = sum(1 for r in rows if r["tag"] in ("delete", "replace") and r["left"] is not None)
    return {"added": added, "removed": removed}


def _file_diff(key: str, filename: str, before: str, after: str,
               before_label: str, after_label: str, lang: str) -> dict[str, Any]:
    rows = _split_rows(before, after)
    stat = _stat_rows(rows)
    return {
        "key": key, "filename": filename, "lang": lang,
        "before_label": before_label, "after_label": after_label,
        "changed": stat["added"] > 0 or stat["removed"] > 0,
        "stat": stat, "rows": rows,
    }


def _git_show(ref: str) -> str:
    try:
        return subprocess.run(["git", "show", ref], cwd=str(REPO),
                              capture_output=True, text=True, timeout=15).stdout
    except Exception:  # noqa: BLE001
        return ""


def _read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


@app.get("/api/demo/source")
async def source():
    """The durable prompt and the baseline v2 adapter, available before any run.

    Lets the dashboard show the code up front, then reveal the live diff after a
    heal completes.
    """
    spec = _file_diff(
        "spec", "context/specs/shipfast/*.json",
        before=_read(SPEC_V2), after=_read(SPEC_V3),
        before_label="openapi.snapshot.json (v2 · 2.4.1)",
        after_label="v3.json (v3 · 3.0.0)", lang="json",
    )
    return {
        "prompt": {
            "filename": "integrations/shipfast/adapter_python.prompt",
            "content": _read(ADAPTER_PROMPT),
            "note": "Durable intent — unchanged by regeneration.",
        },
        "adapter_v2": {
            "filename": ADAPTER_REL,
            "content": _git_show(f"{BASELINE_TAG}:{ADAPTER_REL}"),
            "label": "v2 baseline",
            "lang": "python",
        },
        "spec": spec,
    }


@app.get("/api/demo/diffs/{run_id}")
async def diffs(run_id: str):
    run = _current
    if run is None or run.id != run_id:
        raise HTTPException(status_code=404, detail="Unknown run id")

    adapter = _file_diff(
        "adapter", ADAPTER_REL,
        before=_git_show(f"{BASELINE_TAG}:{ADAPTER_REL}"),
        after=_read(ADAPTER),
        before_label="v2 baseline", after_label="healed v3", lang="python",
    )
    spec = _file_diff(
        "spec", "context/specs/shipfast/*.json",
        before=_read(SPEC_V2), after=_read(SPEC_V3),
        before_label="openapi.snapshot.json (v2 · 2.4.1)",
        after_label="v3.json (v3 · 3.0.0)", lang="json",
    )
    return {
        "files": [adapter, spec],
        "prompt": {
            "filename": "integrations/shipfast/adapter_python.prompt",
            "content": _read(ADAPTER_PROMPT),
            "changed": False,
            "note": "Durable intent — unchanged by regeneration.",
        },
    }


@app.get("/api/health")
async def health():
    running = _current is not None and not _current.done
    return JSONResponse({"status": "ok", "run_active": running,
                         "run_id": _current.id if _current else None})


@app.on_event("shutdown")
async def _shutdown():
    if _current is not None and not _current.done:
        _terminate(_current)
