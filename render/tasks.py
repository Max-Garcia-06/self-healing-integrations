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
