"""Git operations used by analysis and commit-writing flows."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

TEMP_ROOT_NAME = ".git-commit-checks-temp"


def run_git_command(args, repo_path="."):
    """Run a git command in a repository and return trimmed stdout."""
    env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="git-template-") as template_dir:
        env.setdefault("GIT_TEMPLATE_DIR", template_dir)

        completed_process = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    if completed_process.returncode != 0:
        error_message = completed_process.stderr.strip() or completed_process.stdout.strip()
        raise RuntimeError(error_message or "Git command failed.")

    return completed_process.stdout.strip()


def get_recent_commits(repo_path=".", limit=50):
    """Return recent commits with hash, subject, body, and full message fields."""
    log_output = run_git_command(
        ["log", f"-n{limit}", "--pretty=format:%H%x1f%s%x1f%b%x1e"],
        repo_path=repo_path,
    )

    if not log_output:
        return []

    commits = []
    for entry in log_output.split("\x1e"):
        if not entry.strip():
            continue
        parts = entry.split("\x1f", maxsplit=2)
        if len(parts) < 2:
            continue

        commit_hash = parts[0]
        subject = parts[1]
        body = parts[2] if len(parts) > 2 else ""
        clean_body = body.strip()
        message = subject if not clean_body else f"{subject}\n\n{clean_body}"
        commits.append(
            {
                "hash": commit_hash,
                "subject": subject,
                "body": clean_body,
                "message": message,
            }
        )

    return commits


def get_staged_diff(repo_path="."):
    """Return the currently staged diff text."""
    return run_git_command(["diff", "--staged"], repo_path=repo_path)


def get_changed_files(repo_path=".", staged=True):
    """Return changed file paths for staged or unstaged worktree changes."""
    args = ["diff", "--name-only"]
    if staged:
        args.append("--staged")

    output = run_git_command(args, repo_path=repo_path)
    return [line for line in output.splitlines() if line]


def get_diff_stats(repo_path=".", staged=True):
    """Return changed file counts plus insertion and deletion totals."""
    args = ["diff", "--numstat"]
    if staged:
        args.append("--staged")

    output = run_git_command(args, repo_path=repo_path)
    files_changed = 0
    insertions = 0
    deletions = 0

    for line in output.splitlines():
        if not line.strip():
            continue

        added, removed, _path = line.split("\t", maxsplit=2)
        files_changed += 1
        if added.isdigit():
            insertions += int(added)
        if removed.isdigit():
            deletions += int(removed)

    return {
        "files_changed": files_changed,
        "insertions": insertions,
        "deletions": deletions,
    }


def commit_staged_changes(message, repo_path="."):
    """Create a commit from the current staged changes using the provided message."""
    return run_git_command(["commit", "-m", message], repo_path=repo_path)


def clone_remote_repository(url):
    """Clone a repository URL or local path into a temporary directory."""
    temp_root = Path.cwd() / TEMP_ROOT_NAME
    temp_root.mkdir(exist_ok=True)
    clone_path = Path(tempfile.mkdtemp(prefix="repo-", dir=temp_root))
    run_git_command(["clone", "--depth", "50", url, str(clone_path)])
    return clone_path


def prepare_repository(url=None):
    """Return the current repository path or a temporary clone for a provided URL."""
    if url:
        return clone_remote_repository(url)

    return str(Path.cwd().resolve())


def cleanup_repository(repo_path, original_repo="."):
    """Delete a temporary cloned repository while preserving the original repository."""
    repo_path = Path(repo_path).resolve()
    original_repo = Path(original_repo).resolve()

    if repo_path == original_repo:
        return

    if repo_path.exists():
        shutil.rmtree(repo_path)

    temp_root = repo_path.parent
    expected_temp_root = original_repo.parent / TEMP_ROOT_NAME
    if temp_root == expected_temp_root and temp_root.exists() and not any(temp_root.iterdir()):
        temp_root.rmdir()
