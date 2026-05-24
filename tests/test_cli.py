import commit_critic
import pytest


def test_parse_args_supports_analyze_with_url():
    """Argument parsing should support analyze mode with an optional URL."""
    args = commit_critic.parse_args(["--analyze", "--url", "https://example.com/repo.git"])

    assert args.analyze is True
    assert args.write is False
    assert args.url == "https://example.com/repo.git"


def test_format_commit_message_includes_bullets():
    """Commit formatting should append bullets beneath the title."""
    message = commit_critic.format_commit_message("feat: add cache", ["Add Redis support", "Update tests"])

    assert message == "feat: add cache\n\n- Add Redis support\n- Update tests"


def test_run_analyze_reads_commits_and_prints_results(monkeypatch, capsys):
    """Analyze mode should prepare the repo, call the LLM, and print the summary."""
    monkeypatch.setattr(commit_critic.git_ops, "prepare_repository", lambda url=None: "/tmp/repo")
    monkeypatch.setattr(
        commit_critic.git_ops,
        "get_recent_commits",
        lambda repo_path=".", limit=50: [{"subject": "fix: auth bug", "body": ""}],
    )
    monkeypatch.setattr(
        commit_critic.llm,
        "analyze_commits",
        lambda commits: {
            "weak_commits": [
                {
                    "commit": "fixed bug",
                    "score": 2,
                    "issue": "Too vague",
                    "better": "fix(auth): resolve token expiration handling",
                }
            ],
            "strong_commits": [
                {
                    "commit": "feat(api): add Redis caching layer",
                    "score": 9,
                    "why_its_good": "Clear scope and measurable impact",
                }
            ],
            "stats": {
                "average_score": 4.2,
                "vague_commits": 34,
                "vague_percentage": 68,
                "one_word_commits": 12,
                "one_word_percentage": 24,
            },
        },
    )
    cleaned = []
    monkeypatch.setattr(
        commit_critic.git_ops,
        "cleanup_repository",
        lambda repo_path, original_repo=".": cleaned.append((repo_path, original_repo)),
    )

    result = commit_critic.run_analyze(url="https://example.com/repo.git")
    output = capsys.readouterr().out

    assert result == 0
    assert "COMMITS THAT NEED WORK" in output
    assert 'Commit: "fixed bug"' in output
    assert "Average score: 4.2/10" in output
    assert cleaned == [("/tmp/repo", ".")]


def test_run_write_prints_suggestion_and_accepts_default(monkeypatch, capsys):
    """Write mode should show the suggestion and commit the default accepted message."""
    monkeypatch.setattr(commit_critic.git_ops, "get_staged_diff", lambda: "diff --git a/auth.py b/auth.py")
    monkeypatch.setattr(commit_critic.git_ops, "get_changed_files", lambda staged=True: ["auth.py"])
    monkeypatch.setattr(
        commit_critic.git_ops,
        "get_diff_stats",
        lambda staged=True: {"files_changed": 1, "insertions": 4, "deletions": 1},
    )
    monkeypatch.setattr(
        commit_critic.llm,
        "suggest_commit_message",
        lambda diff_text, changed_files=None, diff_stats=None: {
            "changes_detected": ["Modified authentication logic", "Added error handling"],
            "title": "refactor(auth): improve error handling",
            "bullets": ["Add specific error types", "Update tests"],
        },
    )
    committed_messages = []
    monkeypatch.setattr(
        commit_critic.git_ops,
        "commit_staged_changes",
        lambda message: committed_messages.append(message) or "[main abc123] refactor(auth): improve error handling",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    result = commit_critic.run_write()
    output = capsys.readouterr().out

    assert result == 0
    assert "Analyzing staged changes... (1 files changed, +4 -1)" in output
    assert "- Modified authentication logic" in output
    assert "refactor(auth): improve error handling" in output
    assert "- Add specific error types" in output
    assert "Final commit message:" in output
    assert "Commit created successfully." in output
    assert committed_messages == [
        "refactor(auth): improve error handling\n\n- Add specific error types\n- Update tests"
    ]


def test_run_write_commits_custom_message(monkeypatch, capsys):
    """Write mode should commit the custom message when the user overrides the suggestion."""
    monkeypatch.setattr(commit_critic.git_ops, "get_staged_diff", lambda: "diff --git a/auth.py b/auth.py")
    monkeypatch.setattr(commit_critic.git_ops, "get_changed_files", lambda staged=True: ["auth.py"])
    monkeypatch.setattr(
        commit_critic.git_ops,
        "get_diff_stats",
        lambda staged=True: {"files_changed": 1, "insertions": 4, "deletions": 1},
    )
    monkeypatch.setattr(
        commit_critic.llm,
        "suggest_commit_message",
        lambda diff_text, changed_files=None, diff_stats=None: {
            "changes_detected": ["Modified authentication logic"],
            "title": "refactor(auth): improve error handling",
            "bullets": ["Add specific error types"],
        },
    )
    committed_messages = []
    monkeypatch.setattr(
        commit_critic.git_ops,
        "commit_staged_changes",
        lambda message: committed_messages.append(message) or "[main abc123] custom message",
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "custom commit message")

    result = commit_critic.run_write()
    output = capsys.readouterr().out

    assert result == 0
    assert "custom commit message" in output
    assert committed_messages == ["custom commit message"]


def test_run_write_returns_error_when_no_staged_changes(monkeypatch, capsys):
    """Write mode should fail fast if no staged diff is available."""
    monkeypatch.setattr(commit_critic.git_ops, "get_staged_diff", lambda: "")

    result = commit_critic.run_write()
    output = capsys.readouterr().out

    assert result == 1
    assert "No staged changes found." in output


def test_main_rejects_url_for_write_mode():
    """The CLI should reject --url when used with --write."""
    with pytest.raises(SystemExit, match="--url is only supported with --analyze."):
        commit_critic.main(["--write", "--url", "https://example.com/repo.git"])
