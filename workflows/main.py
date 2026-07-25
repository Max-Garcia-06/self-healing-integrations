"""Render Workflows service — connectivity spike.

Defines the single trivial task `verify_render_connection`, used only to prove
we can run a real Render Workflows task (locally and, if account access allows,
in the cloud). It is intentionally NOT connected to ShipFast or the six-stage
self-healing workflow.
"""
from render_sdk import Workflows

app = Workflows()


@app.task
def verify_render_connection(integration_id: str) -> dict:
    """Return a fixed, JSON-serializable health payload for the given integration id."""
    return {
        "integrationId": integration_id,
        "status": "ok",
        "message": "Render Workflows connection verified",
    }


if __name__ == "__main__":
    app.start()
