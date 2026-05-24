import llm
import pytest


def test_load_api_key_prefers_environment_variable(monkeypatch, tmp_path):
    """Environment variables should take priority over the .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text('API_KEY="from-file"\n', encoding="utf-8")
    monkeypatch.setenv("API_KEY", "from-env")

    result = llm.load_api_key(env_path=env_file)

    assert result == "from-env"


def test_load_api_key_reads_env_file_and_strips_quotes(tmp_path, monkeypatch):
    """The .env parser should read quoted API keys correctly."""
    env_file = tmp_path / ".env"
    env_file.write_text('API_KEY="example_123"\n', encoding="utf-8")
    monkeypatch.delenv("API_KEY", raising=False)

    result = llm.load_api_key(env_path=env_file)

    assert result == "example_123"


def test_load_api_key_raises_when_env_file_is_missing(monkeypatch, tmp_path):
    """Missing .env files should raise a readable runtime error."""
    missing_file = tmp_path / ".env"
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Missing environment file"):
        llm.load_api_key(env_path=missing_file)


def test_load_api_key_raises_when_key_is_missing(monkeypatch, tmp_path):
    """Missing API key entries should raise a readable runtime error."""
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_KEY=value\n", encoding="utf-8")
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Missing API_KEY"):
        llm.load_api_key(env_path=env_file)


def test_get_model_name_returns_fixed_model():
    """The scaffold should expose a single fixed model name."""
    assert llm.get_model_name() == llm.MODEL_NAME


def test_build_analysis_prompt_includes_commit_messages():
    """Analysis prompts should include each commit message and JSON instructions."""
    commits = [
        {"subject": "fix: auth bug", "body": ""},
        {"subject": "feat: add cache", "body": "Improve response times"},
    ]

    prompt = llm.build_analysis_prompt(commits)

    assert "weak_commits" in prompt
    assert "strong_commits" in prompt
    assert "Commit 1:" in prompt
    assert "fix: auth bug" in prompt
    assert "feat: add cache\nImprove response times" in prompt


def test_build_write_prompt_includes_files_stats_and_diff():
    """Write prompts should include changed files, diff stats, and diff text."""
    prompt = llm.build_write_prompt(
        diff_text="diff --git a/app.py b/app.py",
        changed_files=["app.py", "tests/test_app.py"],
        diff_stats={"files_changed": 2, "insertions": 8, "deletions": 3},
    )

    assert "summary" in prompt
    assert "title" in prompt
    assert "- app.py" in prompt
    assert "- tests/test_app.py" in prompt
    assert "Files changed: 2" in prompt
    assert "Insertions: 8" in prompt
    assert "Deletions: 3" in prompt
    assert "diff --git a/app.py b/app.py" in prompt


def test_build_messages_creates_system_and_user_entries():
    """Messages should be shaped as a two-message chat exchange."""
    messages = llm.build_messages("hello", system_prompt="system text")

    assert messages == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "hello"},
    ]


def test_build_request_payload_uses_fixed_model_and_default_temperature():
    """Request payloads should use the configured model and message builder."""
    payload = llm.build_request_payload("prompt text")

    assert payload["model"] == llm.MODEL_NAME
    assert payload["temperature"] == 0.2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1] == {"role": "user", "content": "prompt text"}


def test_request_llm_completion_raises_not_implemented():
    """The provider call should remain an explicit scaffold for now."""
    with pytest.raises(NotImplementedError, match="Provider call not implemented yet."):
        llm.request_llm_completion({}, "secret")


def test_parse_json_response_returns_python_data():
    """Valid JSON responses should be parsed into Python objects."""
    response = llm.parse_json_response('{"score": 8, "title": "feat: add cache"}')

    assert response == {"score": 8, "title": "feat: add cache"}


def test_parse_json_response_raises_for_invalid_json():
    """Invalid JSON should raise a value error with a stable message."""
    with pytest.raises(ValueError, match="LLM response was not valid JSON."):
        llm.parse_json_response("not-json")


def test_analyze_commits_builds_payload_and_parses_response(monkeypatch):
    """Commit analysis should load credentials, request a completion, and parse JSON."""
    captured = {}

    monkeypatch.setattr(llm, "load_api_key", lambda: "secret")

    def fake_request(payload, api_key):
        captured["payload"] = payload
        captured["api_key"] = api_key
        return '{"stats": {"average_score": 7.5}}'

    monkeypatch.setattr(llm, "request_llm_completion", fake_request)

    result = llm.analyze_commits([{"subject": "feat: add cache", "body": ""}])

    assert result == {"stats": {"average_score": 7.5}}
    assert captured["api_key"] == "secret"
    assert captured["payload"]["model"] == llm.MODEL_NAME
    assert "feat: add cache" in captured["payload"]["messages"][1]["content"]


def test_suggest_commit_message_builds_payload_and_parses_response(monkeypatch):
    """Commit suggestion should include diff context and parse JSON output."""
    captured = {}

    monkeypatch.setattr(llm, "load_api_key", lambda: "secret")

    def fake_request(payload, api_key):
        captured["payload"] = payload
        captured["api_key"] = api_key
        return '{"title": "refactor(auth): improve error handling", "bullets": ["Add auth validation"]}'

    monkeypatch.setattr(llm, "request_llm_completion", fake_request)

    result = llm.suggest_commit_message(
        diff_text="diff --git a/auth.py b/auth.py",
        changed_files=["auth.py"],
        diff_stats={"files_changed": 1, "insertions": 4, "deletions": 1},
    )

    assert result == {
        "title": "refactor(auth): improve error handling",
        "bullets": ["Add auth validation"],
    }
    assert captured["api_key"] == "secret"
    assert "auth.py" in captured["payload"]["messages"][1]["content"]
    assert "Files changed: 1" in captured["payload"]["messages"][1]["content"]
