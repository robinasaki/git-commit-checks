from pathlib import Path
from subprocess import CompletedProcess

import pytest
import git_ops

def test_run_git_command_returns_trimmed_stdout(monkeypatch):
    """Git commands should return trimmed stdout when they succeed."""
    captured = {}

    def fake_run(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return CompletedProcess(args[0], 0, stdout="main\n", stderr="")

    monkeypatch.setattr(git_ops.subprocess, "run", fake_run)

    result = git_ops.run_git_command(["branch", "--show-current"], repo_path="/repo")

    assert result == "main"
    assert captured["args"][0] == ["git", "branch", "--show-current"]
    assert captured["kwargs"]["cwd"] == "/repo"
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True


def test_run_git_command_raises_runtime_error_on_failure(monkeypatch):
    """Git command failures should raise a readable runtime error."""
    def fake_run(*_args, **_kwargs):
        return CompletedProcess(["git", "status"], 1, stdout="", stderr="fatal: not a git repository")

    monkeypatch.setattr(git_ops.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="fatal: not a git repository"):
        git_ops.run_git_command(["status"])


def test_get_recent_commits_returns_commit_metadata(monkeypatch):
    """Recent commit history should be parsed into structured commit dictionaries."""
    log_output = (
        "a" * 40
        + "\x1f"
        + "fix: add second file"
        + "\x1f"
        + "\x1e"
        + "b" * 40
        + "\x1f"
        + "feat: add first file"
        + "\x1f"
        + "More context here"
        + "\x1e"
    )

    monkeypatch.setattr(git_ops, "run_git_command", lambda args, repo_path=".": log_output)

    commits = git_ops.get_recent_commits(repo_path="/repo", limit=2)

    assert commits == [
        {
            "hash": "a" * 40,
            "subject": "fix: add second file",
            "body": "",
            "message": "fix: add second file",
        },
        {
            "hash": "b" * 40,
            "subject": "feat: add first file",
            "body": "More context here",
            "message": "feat: add first file\n\nMore context here",
        },
    ]


def test_get_staged_diff_requests_staged_patch(monkeypatch):
    """Staged diff helper should delegate to git diff --staged."""
    captured = {}

    def fake_run_git_command(args, repo_path="."):
        captured["args"] = args
        captured["repo_path"] = repo_path
        return "diff --git a/file.txt b/file.txt"

    monkeypatch.setattr(git_ops, "run_git_command", fake_run_git_command)

    diff_text = git_ops.get_staged_diff(repo_path="/repo")

    assert diff_text == "diff --git a/file.txt b/file.txt"
    assert captured == {"args": ["diff", "--staged"], "repo_path": "/repo"}


def test_get_changed_files_uses_staged_flag(monkeypatch):
    """Changed file listing should switch git arguments based on the staged flag."""
    calls = []

    def fake_run_git_command(args, repo_path="."):
        calls.append((args, repo_path))
        return "tracked.txt\nother.py\n"

    monkeypatch.setattr(git_ops, "run_git_command", fake_run_git_command)

    staged_files = git_ops.get_changed_files(repo_path="/repo", staged=True)
    unstaged_files = git_ops.get_changed_files(repo_path="/repo", staged=False)

    assert staged_files == ["tracked.txt", "other.py"]
    assert unstaged_files == ["tracked.txt", "other.py"]
    assert calls == [
        (["diff", "--name-only", "--staged"], "/repo"),
        (["diff", "--name-only"], "/repo"),
    ]


def test_get_diff_stats_summarizes_numstat_output(monkeypatch):
    """Diff stats should count files and numeric insertion and deletion totals."""
    monkeypatch.setattr(
        git_ops,
        "run_git_command",
        lambda args, repo_path=".": "3\t1\tapp.py\n-\t-\timage.png\n2\t0\ttests.py\n",
    )

    stats = git_ops.get_diff_stats(repo_path="/repo", staged=True)

    assert stats == {"files_changed": 3, "insertions": 5, "deletions": 1}


def test_clone_remote_repository_clones_into_hidden_temp_dir(monkeypatch):
    """Cloning should create a temp path and invoke git clone with depth 50."""
    cwd_path = Path("/workspace")
    created_dirs = []
    clone_calls = []

    monkeypatch.setattr(git_ops.Path, "cwd", lambda: cwd_path)

    def fake_mkdir(self, exist_ok=False):
        created_dirs.append((self, exist_ok))

    monkeypatch.setattr(git_ops.Path, "mkdir", fake_mkdir)
    monkeypatch.setattr(git_ops.tempfile, "mkdtemp", lambda prefix, dir: "/workspace/.git-commit-checks-temp/repo-123")

    def fake_run_git_command(args, repo_path="."):
        clone_calls.append((args, repo_path))
        return ""

    monkeypatch.setattr(git_ops, "run_git_command", fake_run_git_command)

    cloned_repo = git_ops.clone_remote_repository("https://example.com/repo.git")

    assert cloned_repo == Path("/workspace/.git-commit-checks-temp/repo-123")
    assert created_dirs == [(Path("/workspace/.git-commit-checks-temp"), True)]
    assert clone_calls == [
        (
            ["clone", "--depth", "50", "https://example.com/repo.git", "/workspace/.git-commit-checks-temp/repo-123"],
            ".",
        )
    ]


def test_prepare_repository_returns_current_repo_without_url(monkeypatch):
    """Preparing without a URL should use the current working directory."""
    monkeypatch.setattr(git_ops.Path, "cwd", lambda: Path("/workspace/repo"))

    prepared_repo = git_ops.prepare_repository()

    assert prepared_repo == "/workspace/repo"


def test_prepare_repository_clones_when_url_is_provided(monkeypatch):
    """Preparing with a URL should delegate to clone_remote_repository."""
    monkeypatch.setattr(git_ops, "clone_remote_repository", lambda url: Path("/tmp/cloned-repo"))

    prepared_repo = git_ops.prepare_repository(url="https://example.com/repo.git")

    assert prepared_repo == Path("/tmp/cloned-repo")


def test_cleanup_repository_removes_temporary_clone(monkeypatch):
    """Cleanup should delete cloned repositories without touching the original repo."""
    removed_paths = []

    monkeypatch.setattr(git_ops.shutil, "rmtree", lambda path: removed_paths.append(path))
    monkeypatch.setattr(git_ops.Path, "exists", lambda self: True)

    git_ops.cleanup_repository("/tmp/cloned-repo", original_repo="/workspace/source-repo")

    assert removed_paths == [Path("/tmp/cloned-repo").resolve()]


def test_cleanup_repository_skips_original_repo(monkeypatch):
    """Cleanup should not remove the original repository path."""
    removed_paths = []

    monkeypatch.setattr(git_ops.shutil, "rmtree", lambda path: removed_paths.append(path))

    git_ops.cleanup_repository("/workspace/repo", original_repo="/workspace/repo")

    assert removed_paths == []
