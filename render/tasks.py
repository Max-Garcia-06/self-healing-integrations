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
CONFIG_PATH = REPO_ROOT / "src" / "config" / "shipfast.py"
PROMPT_PATH = REPO_ROOT / "integrations" / "shipfast" / "adapter_python.prompt"
SPEC_PATH = REPO_ROOT / "context" / "specs" / "shipfast" / "openapi.snapshot.json"
V3_SPEC_PATH = REPO_ROOT / "context" / "specs" / "shipfast" / "v3.json"

_GITHUB_REPO = "https://github.com/Max-Garcia-06/self-healing-integrations.git"

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


def _git(*args: str) -> subprocess.CompletedProcess:
    """Run a git command against REPO_ROOT without ever waiting on an auth prompt."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )


def sync_repo() -> None:
    """Fast-forward the local checkout to origin/main.

    Render Workflows task runs don't share a filesystem — each chained
    task in the same run gets a fresh checkout from the built image, not
    whatever a sibling task wrote to disk. Tasks that need to see
    `regenerate_adapter`'s pushed commit must pull first.
    """
    _git("fetch", "origin", "main")
    _git("reset", "--hard", "origin/main")


def _commit_and_push_regeneration() -> dict:
    """Commit and push the freshly regenerated adapter and config.

    Needed so `verify_healed` and `evidence` — each running on their own
    fresh checkout — can see what this task just produced locally.

    Returns:
        `committed` (False if regeneration produced no diff, in which case
        there's nothing to push) and, when True, the pushed commit `sha`.

    Raises:
        RuntimeError: If GITHUB_TOKEN is unset, or the commit/push itself
            fails, so the caller can fail the task instead of silently
            leaving sibling tasks unable to observe the regeneration.
    """
    _git("config", "user.email", "self-heal@render.workflow")
    _git("config", "user.name", "Self-Heal Bot")
    _git("add", "--", str(ADAPTER_PATH), str(CONFIG_PATH))

    commit = _git("commit", "-m", "chore(self-heal): regenerate ShipFast adapter for vendor spec change")
    if commit.returncode != 0:
        if "nothing to commit" in commit.stdout:
            return {"committed": False}
        raise RuntimeError(f"git commit failed: {commit.stderr or commit.stdout}")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set; cannot push the regenerated adapter")

    push_url = _GITHUB_REPO.replace("https://", f"https://x-access-token:{token}@")
    push = _git("push", push_url, "HEAD:main")
    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push.stderr}")

    sha = _git("rev-parse", "HEAD").stdout.strip()
    return {"committed": True, "sha": sha}


def regenerate_adapter() -> dict:
    """Run scripts/pdd_regen.sh, then commit and push the result.

    Returns:
        `ok`, the process return code, truncated stdout/stderr for
        diagnostics, and (on success) `publish` describing the commit. If
        publishing fails, `ok` is forced False and `publish_error` is set,
        since sibling tasks won't be able to see an unpublished change.
    """
    result = subprocess.run(
        ["bash", "scripts/pdd_regen.sh"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    regen = {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }
    if not regen["ok"]:
        return regen

    try:
        regen["publish"] = _commit_and_push_regeneration()
    except RuntimeError as exc:
        regen["ok"] = False
        regen["publish_error"] = str(exc)
    return regen


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
    sync_repo()
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
    sync_repo()
    adapter_after = ADAPTER_PATH.read_text()
    prompt_after = PROMPT_PATH.read_text()
    return {
        "prompt_intent_unchanged": _strip_pin_lines(prompt_before) == _strip_pin_lines(prompt_after),
        "adapter_changed": adapter_before != adapter_after,
        "spec_changed": SPEC_PATH.read_text() != V3_SPEC_PATH.read_text(),
    }
