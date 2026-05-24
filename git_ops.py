def run_git_command(args, repo_path="."):
    """Run a git command, return its output."""
    pass


def get_recent_commits(repo_path=".", limit=50):
    """Return the most recent commit messages and metadata."""
    pass


def get_staged_diff(repo_path="."):
    """Return the staged diff text."""
    pass


def get_changed_files(repo_path=".", staged=True):
    """Return the changed file paths."""
    pass


def get_diff_stats(repo_path=".", staged=True):
    """Return a compact summary of file, insertion, and deletion counts."""
    pass


def clone_remote_repository(url):
    """Clone a remote repository into a temporary directory."""
    pass


def prepare_repository(url=None):
    """Return the repository path to analyze, using the current repo or a cloned remote repo."""
    pass


def cleanup_repository(repo_path, original_repo="."):
    """Remove temporary repository resources created."""
    pass
