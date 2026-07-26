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
