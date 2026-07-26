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
    monkeypatch.setattr(tasks, "_commit_and_push_regeneration", lambda: {"committed": True, "sha": "abc123"})
    result = tasks.regenerate_adapter()
    assert result == {
        "ok": True,
        "returncode": 0,
        "stdout": "done",
        "stderr": "",
        "publish": {"committed": True, "sha": "abc123"},
    }


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


def test_regenerate_adapter_publish_failure_marks_not_ok(monkeypatch):
    monkeypatch.setattr(
        tasks.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="done", stderr=""),
    )

    def raise_publish_error():
        raise RuntimeError("GITHUB_TOKEN is not set; cannot push the regenerated adapter")

    monkeypatch.setattr(tasks, "_commit_and_push_regeneration", raise_publish_error)
    result = tasks.regenerate_adapter()
    assert result["ok"] is False
    assert "GITHUB_TOKEN" in result["publish_error"]


def test_sync_repo_fetches_and_resets_to_origin_main(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tasks.subprocess,
        "run",
        lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    tasks.sync_repo()
    assert calls == [
        ["git", "fetch", "origin", "main"],
        ["git", "reset", "--hard", "origin/main"],
    ]


def test_commit_and_push_regeneration_success(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    calls = []

    def fake_run(cmd, **k):
        calls.append(cmd)
        if cmd[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="deadbeef\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tasks.subprocess, "run", fake_run)
    result = tasks._commit_and_push_regeneration()

    assert result == {"committed": True, "sha": "deadbeef"}
    push_call = next(c for c in calls if c[:2] == ["git", "push"])
    assert "test-token" in push_call[2]
    assert push_call[3] == "HEAD:main"


def test_commit_and_push_regeneration_nothing_to_commit(monkeypatch):
    def fake_run(cmd, **k):
        if cmd[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="nothing to commit, working tree clean", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tasks.subprocess, "run", fake_run)
    result = tasks._commit_and_push_regeneration()
    assert result == {"committed": False}


def test_commit_and_push_regeneration_missing_token_raises(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_run(cmd, **k):
        if cmd[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tasks.subprocess, "run", fake_run)
    try:
        tasks._commit_and_push_regeneration()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "GITHUB_TOKEN" in str(exc)


def test_commit_and_push_regeneration_push_failure_raises(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    def fake_run(cmd, **k):
        if cmd[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="remote rejected")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(tasks.subprocess, "run", fake_run)
    try:
        tasks._commit_and_push_regeneration()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "remote rejected" in str(exc)


def test_verify_healed_true(monkeypatch):
    monkeypatch.setattr(tasks, "sync_repo", lambda: None)
    monkeypatch.setattr(tasks, "run_adapter", lambda url: {"kind": "ADAPTER_OK", "amount": "1240", "currency": "USD"})
    result = tasks.verify_healed("http://mock:8081")
    assert result["healed"] is True


def test_verify_healed_false_on_wrong_amount(monkeypatch):
    monkeypatch.setattr(tasks, "sync_repo", lambda: None)
    monkeypatch.setattr(tasks, "run_adapter", lambda url: {"kind": "ADAPTER_OK", "amount": "990", "currency": "USD"})
    result = tasks.verify_healed("http://mock:8081")
    assert result["healed"] is False


def test_verify_healed_false_on_error(monkeypatch):
    monkeypatch.setattr(tasks, "sync_repo", lambda: None)
    monkeypatch.setattr(
        tasks, "run_adapter", lambda url: {"kind": "ADAPTER_ERROR", "amount": "NoServiceAvailable", "currency": "410 Gone"}
    )
    result = tasks.verify_healed("http://mock:8081")
    assert result["healed"] is False


def test_evidence_all_true(monkeypatch, tmp_path):
    monkeypatch.setattr(tasks, "sync_repo", lambda: None)
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
    monkeypatch.setattr(tasks, "sync_repo", lambda: None)
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
