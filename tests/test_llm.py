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

    assert "changes_detected" in prompt
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


def test_build_request_payload_uses_fixed_model_and_messages():
    """Request payloads should only include the fixed model and chat messages."""
    payload = llm.build_request_payload("prompt text")

    assert payload["model"] == llm.MODEL_NAME
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1] == {"role": "user", "content": "prompt text"}
    assert set(payload) == {"model", "messages"}


def test_request_llm_completion_calls_openai_api(monkeypatch):
    """Provider requests should be translated into the OpenAI SDK call."""
    payload = llm.build_request_payload("prompt text")
    captured = {}

    class FakeCompletions:
        def create(self, model, messages):
            captured["model"] = model
            captured["messages"] = messages
            return type(
                "Response",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type(
                                    "Message",
                                    (),
                                    {"content": '{"title": "feat: add cache"}'},
                                )()
                            },
                        )()
                    ]
                },
            )()

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm, "OpenAI", FakeClient)

    result = llm.request_llm_completion(payload, "secret-key")

    assert result == '{"title": "feat: add cache"}'
    assert captured["api_key"] == "secret-key"
    assert captured["model"] == llm.MODEL_NAME
    assert captured["messages"][0]["content"] == llm.SYSTEM_PROMPT
    assert captured["messages"][1]["content"] == "prompt text"


def test_request_llm_completion_raises_runtime_error_for_http_failures(monkeypatch):
    """HTTP failures should be converted into readable runtime errors."""
    payload = llm.build_request_payload("prompt text")

    class FakeAPIStatusError(Exception):
        def __init__(self, response_text):
            super().__init__(response_text)
            self.response = type("Response", (), {"text": response_text})()

    class FakeCompletions:
        def create(self, model, messages):
            raise FakeAPIStatusError('{"error":"bad request"}')

    class FakeClient:
        def __init__(self, api_key):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm, "APIStatusError", FakeAPIStatusError)
    monkeypatch.setattr(llm, "OpenAI", FakeClient)

    with pytest.raises(RuntimeError, match="OpenAI request failed"):
        llm.request_llm_completion(payload, "secret-key")


def test_parse_json_response_returns_python_data():
    """Valid JSON responses should be parsed into Python objects."""
    response = llm.parse_json_response('{"score": 8, "title": "feat: add cache"}')

    assert response == {"score": 8, "title": "feat: add cache"}


def test_parse_json_response_handles_code_fences():
    """JSON wrapped in code fences should still parse successfully."""
    response = llm.parse_json_response('```json\n{"score": 8}\n```')

    assert response == {"score": 8}


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
        return (
            '{"changes_detected": ["Updated authentication flow"], '
            '"title": "refactor(auth): improve error handling", '
            '"bullets": ["Add auth validation"]}'
        )

    monkeypatch.setattr(llm, "request_llm_completion", fake_request)

    result = llm.suggest_commit_message(
        diff_text="diff --git a/auth.py b/auth.py",
        changed_files=["auth.py"],
        diff_stats={"files_changed": 1, "insertions": 4, "deletions": 1},
    )

    assert result == {
        "changes_detected": ["Updated authentication flow"],
        "title": "refactor(auth): improve error handling",
        "bullets": ["Add auth validation"],
    }
    assert captured["api_key"] == "secret"
    assert "auth.py" in captured["payload"]["messages"][1]["content"]
    assert "Files changed: 1" in captured["payload"]["messages"][1]["content"]
