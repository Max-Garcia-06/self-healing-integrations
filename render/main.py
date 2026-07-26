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
