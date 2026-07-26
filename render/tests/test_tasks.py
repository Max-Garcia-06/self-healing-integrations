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
