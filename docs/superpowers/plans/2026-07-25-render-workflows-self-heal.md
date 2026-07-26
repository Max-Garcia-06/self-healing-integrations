# Render Workflows Self-Heal Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing six-stage self-healing flow into a real Render Workflows service (`render/`) as four chained tasks, separate from Lawrence's `workflows/` connectivity spike.

**Architecture:** Framework-free logic lives in `render/tasks.py` (plain functions, subprocess calls into `scripts/run_adapter.py` and `scripts/pdd_regen.sh`, unit-testable without `render_sdk` installed). `render/main.py` wraps each function as an `@app.task` and adds an async `self_heal` orchestrator that chains them per the Render SDK's task-calls-task pattern.

**Tech Stack:** Python 3.11+, `render_sdk>=0.6.0`, `pytest`, `subprocess`, existing repo scripts.

## Global Constraints

- Never edit `workflows/`, `mock_upstream/`, `sponsors/`, `fixtures/` (Lawrence's).
- Never run any `pdd` subcommand directly, including indirectly by executing `regenerate_adapter()` or `self_heal()` at test time — those are exercised by mocking `subprocess.run`, never invoked for real in this plan.
- All functions get type hints and docstrings (Google style); catch specific exceptions only; no bare `except`.
- `mock_base_url` is caller-supplied; the workflow itself never starts, stops, or resets the mock/git baseline — that stays `scripts/demo.sh`'s job.

---

### Task 1: `run_adapter` + `detect_break`

**Files:**
- Create: `render/tasks.py`
- Test: `render/tests/test_tasks.py`

**Interfaces:**
- Produces: `run_adapter(mock_base_url: str) -> dict` with keys `kind`, `amount`, `currency`. `detect_break(mock_base_url: str) -> dict` with keys `broken` (bool), `result` (the `run_adapter` dict), `adapter_before` (str), `prompt_before` (str). Module-level constants `REPO_ROOT`, `ADAPTER_PATH`, `PROMPT_PATH`, `SPEC_PATH`, `V3_SPEC_PATH` (all `pathlib.Path`), and the `subprocess` module imported at module scope (tests monkeypatch `tasks.subprocess.run`, `tasks.ADAPTER_PATH`, `tasks.PROMPT_PATH`).

- [ ] **Step 1: Write the failing tests**

```python
# render/tests/test_tasks.py
import subprocess

from render import tasks


def test_run_adapter_parses_ok(monkeypatch):
    captured_env = {}

    def fake_run(cmd, cwd, env, capture_output, text, check):
        captured_env.update(env)
        return subprocess.CompletedProcess(cmd, 0, stdout="ADAPTER_OK::1240::USD\n", stderr="")

    monkeypatch.setattr(tasks.subprocess, "run", fake_run)
    result = tasks.run_adapter("http://mock:8081")

    assert result == {"kind": "ADAPTER_OK", "amount": "1240", "currency": "USD"}
    assert captured_env["SHIPFAST_BASE_URL"] == "http://mock:8081"


def test_run_adapter_parses_error(monkeypatch):
    monkeypatch.setattr(
        tasks.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 20, stdout="ADAPTER_ERROR::NoServiceAvailable::410 Gone\n", stderr=""
        ),
    )
    result = tasks.run_adapter("http://mock:8081")
    assert result == {"kind": "ADAPTER_ERROR", "amount": "NoServiceAvailable", "currency": "410 Gone"}


def test_detect_break_true_when_adapter_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        tasks,
        "run_adapter",
        lambda url: {"kind": "ADAPTER_ERROR", "amount": "NoServiceAvailable", "currency": "410 Gone"},
    )
    adapter_file = tmp_path / "adapter.py"
    prompt_file = tmp_path / "adapter.prompt"
    adapter_file.write_text("old adapter")
    prompt_file.write_text("old prompt")
    monkeypatch.setattr(tasks, "ADAPTER_PATH", adapter_file)
    monkeypatch.setattr(tasks, "PROMPT_PATH", prompt_file)

    result = tasks.detect_break("http://mock:8081")

    assert result["broken"] is True
    assert result["adapter_before"] == "old adapter"
    assert result["prompt_before"] == "old prompt"


def test_detect_break_false_when_adapter_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(tasks, "run_adapter", lambda url: {"kind": "ADAPTER_OK", "amount": "1240", "currency": "USD"})
    adapter_file = tmp_path / "a.py"
    prompt_file = tmp_path / "p.prompt"
    adapter_file.write_text("x")
    prompt_file.write_text("y")
    monkeypatch.setattr(tasks, "ADAPTER_PATH", adapter_file)
    monkeypatch.setattr(tasks, "PROMPT_PATH", prompt_file)

    result = tasks.detect_break("http://mock:8081")
    assert result["broken"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'render'` (or `tasks`) — nothing exists yet.

- [ ] **Step 3: Write minimal implementation**

```python
# render/tasks.py
"""Framework-free task logic for the Render Workflows self-heal service.

Kept free of the `render_sdk` import so it's unit-testable without it.
`render/main.py` wraps these as `@app.task` entry points.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import TypedDict

REPO_ROOT = Path(__file__).resolve().parent.parent

ADAPTER_PATH = REPO_ROOT / "integrations" / "shipfast" / "adapter.py"
PROMPT_PATH = REPO_ROOT / "integrations" / "shipfast" / "adapter_python.prompt"
SPEC_PATH = REPO_ROOT / "context" / "specs" / "shipfast" / "openapi.snapshot.json"
V3_SPEC_PATH = REPO_ROOT / "context" / "specs" / "shipfast" / "v3.json"

_DEMO_ENV = {
    "SHIPFAST_API_KEY": "demo-key",
    "SHIPFAST_ACCOUNT_NUMBER": "DEMO-ACCT-0001",
    "SHIPFAST_SHIPPER_ID": "shipper-123",
}

_PIN_LINE = re.compile(r"<include|openapi\.snapshot\.json|v3\.json")


class AdapterResult(TypedDict):
    kind: str
    amount: str
    currency: str


def run_adapter(mock_base_url: str) -> AdapterResult:
    """Run scripts/run_adapter.py against a mock and parse its output line.

    Args:
        mock_base_url: Base URL of a running ShipFast mock.

    Returns:
        Parsed ADAPTER_OK / ADAPTER_ERROR / ADAPTER_FATAL result.
    """
    env = os.environ.copy()
    env["SHIPFAST_BASE_URL"] = mock_base_url
    env.update(_DEMO_ENV)
    result = subprocess.run(
        ["uv", "run", "python", "scripts/run_adapter.py"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    kind, _, rest = result.stdout.strip().partition("::")
    amount, _, currency = rest.partition("::")
    return {"kind": kind, "amount": amount, "currency": currency}


def detect_break(mock_base_url: str) -> dict:
    """Confirm the adapter currently fails against mock_base_url and snapshot pre-regen state.

    Args:
        mock_base_url: Base URL of a running ShipFast mock, expected to be on v3.

    Returns:
        `broken`, the raw adapter result, and the adapter/prompt contents
        from before any regeneration (needed later by `evidence`).
    """
    result = run_adapter(mock_base_url)
    return {
        "broken": result["kind"] != "ADAPTER_OK",
        "result": result,
        "adapter_before": ADAPTER_PATH.read_text(),
        "prompt_before": PROMPT_PATH.read_text(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add render/tasks.py render/tests/test_tasks.py
git commit -m "feat(render): add run_adapter and detect_break task logic"
```

---

### Task 2: `regenerate_adapter`

**Files:**
- Modify: `render/tasks.py`
- Modify: `render/tests/test_tasks.py`

**Interfaces:**
- Consumes: `REPO_ROOT` from Task 1.
- Produces: `regenerate_adapter() -> dict` with keys `ok` (bool), `returncode` (int), `stdout` (str), `stderr` (str).

- [ ] **Step 1: Write the failing tests**

```python
# append to render/tests/test_tasks.py
def test_regenerate_adapter_ok(monkeypatch):
    monkeypatch.setattr(
        tasks.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="done", stderr=""),
    )
    result = tasks.regenerate_adapter()
    assert result == {"ok": True, "returncode": 0, "stdout": "done", "stderr": ""}


def test_regenerate_adapter_failure(monkeypatch):
    monkeypatch.setattr(
        tasks.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="boom"),
    )
    result = tasks.regenerate_adapter()
    assert result["ok"] is False
    assert result["returncode"] == 1
    assert result["stderr"] == "boom"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v -k regenerate`
Expected: FAIL with `AttributeError: module 'render.tasks' has no attribute 'regenerate_adapter'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to render/tasks.py
def regenerate_adapter() -> dict:
    """Run scripts/pdd_regen.sh to regenerate the adapter and config from their prompts.

    Returns:
        `ok`, the process return code, and truncated stdout/stderr for
        diagnostics (Render task outputs must stay JSON-serializable and
        reasonably small).
    """
    result = subprocess.run(
        ["bash", "scripts/pdd_regen.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v -k regenerate`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add render/tasks.py render/tests/test_tasks.py
git commit -m "feat(render): add regenerate_adapter task logic"
```

---

### Task 3: `verify_healed` + `evidence`

**Files:**
- Modify: `render/tasks.py`
- Modify: `render/tests/test_tasks.py`

**Interfaces:**
- Consumes: `run_adapter`, `ADAPTER_PATH`, `PROMPT_PATH`, `SPEC_PATH`, `V3_SPEC_PATH`, `_PIN_LINE` from Task 1.
- Produces: `verify_healed(mock_base_url: str, expected_amount: str = "1240", expected_currency: str = "USD") -> dict` with key `healed` (bool) plus `result`. `evidence(adapter_before: str, prompt_before: str) -> dict` with keys `prompt_intent_unchanged`, `adapter_changed`, `spec_changed` (all bool).

- [ ] **Step 1: Write the failing tests**

```python
# append to render/tests/test_tasks.py
def test_verify_healed_true(monkeypatch):
    monkeypatch.setattr(tasks, "run_adapter", lambda url: {"kind": "ADAPTER_OK", "amount": "1240", "currency": "USD"})
    result = tasks.verify_healed("http://mock:8081")
    assert result["healed"] is True


def test_verify_healed_false_on_wrong_amount(monkeypatch):
    monkeypatch.setattr(tasks, "run_adapter", lambda url: {"kind": "ADAPTER_OK", "amount": "990", "currency": "USD"})
    result = tasks.verify_healed("http://mock:8081")
    assert result["healed"] is False


def test_verify_healed_false_on_error(monkeypatch):
    monkeypatch.setattr(
        tasks, "run_adapter", lambda url: {"kind": "ADAPTER_ERROR", "amount": "NoServiceAvailable", "currency": "410 Gone"}
    )
    result = tasks.verify_healed("http://mock:8081")
    assert result["healed"] is False


def test_evidence_all_true(monkeypatch, tmp_path):
    adapter_after = tmp_path / "adapter.py"
    prompt_after = tmp_path / "adapter.prompt"
    spec = tmp_path / "spec.json"
    v3 = tmp_path / "v3.json"
    adapter_after.write_text("new adapter")
    prompt_after.write_text("<include ../spec.json>\nsame intent")
    spec.write_text('{"a":1}')
    v3.write_text('{"a":2}')
    monkeypatch.setattr(tasks, "ADAPTER_PATH", adapter_after)
    monkeypatch.setattr(tasks, "PROMPT_PATH", prompt_after)
    monkeypatch.setattr(tasks, "SPEC_PATH", spec)
    monkeypatch.setattr(tasks, "V3_SPEC_PATH", v3)

    result = tasks.evidence(
        adapter_before="old adapter",
        prompt_before="<include ../old_spec.json>\nsame intent",
    )

    assert result == {"prompt_intent_unchanged": True, "adapter_changed": True, "spec_changed": True}


def test_evidence_detects_changed_intent(monkeypatch, tmp_path):
    adapter_after = tmp_path / "adapter.py"
    prompt_after = tmp_path / "adapter.prompt"
    spec = tmp_path / "spec.json"
    v3 = tmp_path / "v3.json"
    adapter_after.write_text("same adapter")
    prompt_after.write_text("<include ../spec.json>\ndifferent intent now")
    spec.write_text("{}")
    v3.write_text("{}")
    monkeypatch.setattr(tasks, "ADAPTER_PATH", adapter_after)
    monkeypatch.setattr(tasks, "PROMPT_PATH", prompt_after)
    monkeypatch.setattr(tasks, "SPEC_PATH", spec)
    monkeypatch.setattr(tasks, "V3_SPEC_PATH", v3)

    result = tasks.evidence(adapter_before="same adapter", prompt_before="<include ../old.json>\noriginal intent")

    assert result["prompt_intent_unchanged"] is False
    assert result["adapter_changed"] is False
    assert result["spec_changed"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v -k "verify_healed or evidence"`
Expected: FAIL with `AttributeError: module 'render.tasks' has no attribute 'verify_healed'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to render/tasks.py
def verify_healed(
    mock_base_url: str, expected_amount: str = "1240", expected_currency: str = "USD"
) -> dict:
    """Confirm the adapter now succeeds against mock_base_url with the expected quote.

    Args:
        mock_base_url: Base URL of a running ShipFast mock.
        expected_amount: Expected quote amount in minor units, as a string
            (matches `run_adapter`'s string output).
        expected_currency: Expected quote currency code.

    Returns:
        `healed` and the raw adapter result.
    """
    result = run_adapter(mock_base_url)
    healed = (
        result["kind"] == "ADAPTER_OK"
        and result["amount"] == expected_amount
        and result["currency"] == expected_currency
    )
    return {"healed": healed, "result": result}


def _strip_pin_lines(text: str) -> str:
    """Drop vendor-spec-pin lines so intent comparisons ignore which spec is pinned."""
    return "\n".join(line for line in text.splitlines() if not _PIN_LINE.search(line))


def evidence(adapter_before: str, prompt_before: str) -> dict:
    """Diff pre/post regeneration state into the four self-heal claims.

    Args:
        adapter_before: `adapter.py` contents captured by `detect_break`,
            before regeneration.
        prompt_before: The adapter's `.prompt` contents captured by
            `detect_break`, before regeneration.

    Returns:
        `prompt_intent_unchanged`, `adapter_changed`, `spec_changed`.
    """
    adapter_after = ADAPTER_PATH.read_text()
    prompt_after = PROMPT_PATH.read_text()
    return {
        "prompt_intent_unchanged": _strip_pin_lines(prompt_before) == _strip_pin_lines(prompt_after),
        "adapter_changed": adapter_before != adapter_after,
        "spec_changed": SPEC_PATH.read_text() != V3_SPEC_PATH.read_text(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v`
Expected: 10 passed (all tests from Tasks 1-3)

- [ ] **Step 5: Commit**

```bash
git add render/tasks.py render/tests/test_tasks.py
git commit -m "feat(render): add verify_healed and evidence task logic"
```

---

### Task 4: Render Workflows service (`main.py`)

**Files:**
- Create: `render/main.py`
- Create: `render/requirements.txt`

**Interfaces:**
- Consumes: `tasks.detect_break`, `tasks.regenerate_adapter`, `tasks.verify_healed`, `tasks.evidence` from Tasks 1-3.
- Produces: Render Workflows tasks `detect_break`, `regenerate_adapter`, `verify_healed`, `evidence`, `self_heal` — importable as `render/main.py`, run via `app.start()`.

No automated test here: this file's only job is thin `render_sdk` wrapping, and `render_sdk` needs a real (or `render workflows dev --local`) environment to execute — that's Task 5's manual verification, not a unit test. Keep this task's diff to wrapper-only code; the logic under test already lives in `tasks.py`.

- [ ] **Step 1: Write `render/requirements.txt`**

```
render_sdk>=0.6.0
```

- [ ] **Step 2: Write `render/main.py`**

```python
"""Render Workflows service — real self-heal orchestration for ShipFast.

Chains render/tasks.py's framework-free logic into Render Workflows tasks.
Separate from workflows/main.py (Lawrence's connectivity spike): this one
assumes a ShipFast mock already exists and already broke on v3, and proves
the actual six-stage self-heal against it.
"""
from __future__ import annotations

from render_sdk import Workflows

from render import tasks

app = Workflows()


@app.task
def detect_break(mock_base_url: str) -> dict:
    """Confirm the adapter currently fails against mock_base_url."""
    return tasks.detect_break(mock_base_url)


@app.task
def regenerate_adapter() -> dict:
    """Run PDD to regenerate the adapter and config from their prompts."""
    return tasks.regenerate_adapter()


@app.task
def verify_healed(mock_base_url: str) -> dict:
    """Confirm the adapter now succeeds against mock_base_url."""
    return tasks.verify_healed(mock_base_url)


@app.task
def evidence(adapter_before: str, prompt_before: str) -> dict:
    """Diff pre/post regeneration state into the four self-heal claims."""
    return tasks.evidence(adapter_before, prompt_before)


@app.task
async def self_heal(mock_base_url: str) -> dict:
    """Orchestrate the full self-heal: detect, regenerate, verify, prove it.

    Assumes mock_base_url is already serving v3 and the deployed adapter is
    stale — this task does not manage mock lifecycle. Short-circuits if the
    adapter isn't actually broken, and again if regeneration fails, so
    partial state is always visible in the result.

    Args:
        mock_base_url: Base URL of a running ShipFast mock, already on v3.

    Returns:
        `status` (`skipped` / `regen_failed` / `healed` / `incomplete`) plus
        every stage's result for evidence.
    """
    detected = await detect_break(mock_base_url)
    if not detected["broken"]:
        return {"status": "skipped", "reason": "adapter not broken against this mock", "detected": detected}

    regen = await regenerate_adapter()
    if not regen["ok"]:
        return {"status": "regen_failed", "detected": detected, "regen": regen}

    verified = await verify_healed(mock_base_url)
    ev = await evidence(detected["adapter_before"], detected["prompt_before"])

    healed = verified["healed"] and ev["adapter_changed"] and ev["prompt_intent_unchanged"]
    return {
        "status": "healed" if healed else "incomplete",
        "detected": detected,
        "regen": regen,
        "verified": verified,
        "evidence": ev,
    }


if __name__ == "__main__":
    app.start()
```

- [ ] **Step 3: Verify the module imports cleanly (syntax/name check only — render_sdk not required for this check)**

Run: `python3 -c "import ast; ast.parse(open('render/main.py').read())"`
Expected: no output, exit 0

- [ ] **Step 4: Commit**

```bash
git add render/main.py render/requirements.txt
git commit -m "feat(render): wire self-heal tasks into a Render Workflows service"
```

---

### Task 5: README + local verification

**Files:**
- Create: `render/README.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Write `render/README.md`**

```markdown
# Render Workflows — self-heal orchestration

Real six-stage self-heal, wired as Render Workflows tasks. Separate from
`../workflows/` (Lawrence's connectivity spike — do not merge these).

- **Assumes** a ShipFast mock is already running and already broke on v3 —
  this service does not start/stop the mock or touch git state. Use
  `scripts/demo.sh` (steps 1-4) to get a mock into that state first, or
  point at your own.
- Tasks: `detect_break`, `regenerate_adapter`, `verify_healed`, `evidence`,
  and the orchestrator `self_heal` that chains all four.

## Local run (no Render account required)

From this `render/` directory:

\`\`\`bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# terminal A — task server on a different port than Lawrence's spike (8120)
render workflows dev --port 8121 -- .venv/bin/python main.py

# terminal B — get a mock into the broken-v3 state, e.g. by running
# scripts/demo.sh from the repo root and letting it stop at STEP 5 (it
# leaves the mock running and broken on v3 until you Ctrl-C it)

render workflows tasks runs start detect_break --local \
  --input='["http://127.0.0.1:8081"]' -o json
# -> expect {"broken": true, ...}

render workflows tasks runs start self_heal --local \
  --input='["http://127.0.0.1:8081"]' -o json
# -> this one actually shells out to scripts/pdd_regen.sh (a real PDD call)
\`\`\`

## Cloud deploy (for hackathon submission proof)

Needs, beyond this service:

1. **A public mock.** `../mock/server.py` deployed as its own Render Web
   Service (build: `pip install -r ../mock/requirements.txt` or equivalent;
   run: `uvicorn mock.server:app --host 0.0.0.0 --port $PORT`) so
   `mock_base_url` isn't `localhost`.
2. **`pdd-cli` in the build.** It's a global tool on dev machines today, not
   in `pyproject.toml` — add `uv tool install pdd-cli` (or `pip install
   pdd-cli`) to the build command.
3. **An LLM API key** for `pdd-cli`, set as a Render secret env var (check
   your local `pdd` setup for which one it reads).

\`\`\`bash
render login
render workspace set

render workflows create \
  --name self-heal-orchestration \
  --runtime python \
  --build-command "pip install -r render/requirements.txt && uv tool install pdd-cli" \
  --run-command ".venv/bin/python render/main.py" \
  --repo . \
  --region oregon \
  -o json

render workflows tasks runs start self_heal \
  --input='["https://<your-deployed-mock>.onrender.com"]' -o json
# -> note the run id as submission proof
\`\`\`
```

- [ ] **Step 2: Run the full test suite one more time**

Run: `cd render && uv run --with pytest pytest tests/test_tasks.py -v`
Expected: 10 passed

- [ ] **Step 3: Commit**

```bash
git add render/README.md
git commit -m "docs(render): add setup, local run, and cloud deploy instructions"
```
