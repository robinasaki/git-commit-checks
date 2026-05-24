import inspect

import pytest

import git_ops


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    [
        ("run_git_command", ["args", "repo_path"]),
        ("get_recent_commits", ["repo_path", "limit"]),
        ("get_staged_diff", ["repo_path"]),
        ("get_changed_files", ["repo_path", "staged"]),
        ("get_diff_stats", ["repo_path", "staged"]),
        ("clone_remote_repository", ["url"]),
        ("prepare_repository", ["url"]),
        ("cleanup_repository", ["repo_path", "original_repo"]),
    ],
)
def test_git_ops_function_signatures(func_name, expected_params):
    """Each public git helper should expose the expected arguments."""
    func = getattr(git_ops, func_name)
    signature = inspect.signature(func)

    assert list(signature.parameters) == expected_params


@pytest.mark.parametrize(
    ("func_name", "expected_defaults"),
    [
        ("run_git_command", {"repo_path": "."}),
        ("get_recent_commits", {"repo_path": ".", "limit": 50}),
        ("get_staged_diff", {"repo_path": "."}),
        ("get_changed_files", {"repo_path": ".", "staged": True}),
        ("get_diff_stats", {"repo_path": ".", "staged": True}),
        ("prepare_repository", {"url": None}),
        ("cleanup_repository", {"original_repo": "."}),
    ],
)
def test_git_ops_default_values(func_name, expected_defaults):
    """Default argument values should support the intended CLI flows."""
    func = getattr(git_ops, func_name)
    parameters = inspect.signature(func).parameters

    defaults = {
        name: parameter.default
        for name, parameter in parameters.items()
        if parameter.default is not inspect.Parameter.empty
    }

    assert defaults == expected_defaults


@pytest.mark.parametrize(
    "func_name",
    [
        "run_git_command",
        "get_recent_commits",
        "get_staged_diff",
        "get_changed_files",
        "get_diff_stats",
        "clone_remote_repository",
        "prepare_repository",
        "cleanup_repository",
    ],
)
def test_git_ops_functions_have_docstrings(func_name):
    """Public helpers should document their responsibility."""
    func = getattr(git_ops, func_name)

    assert func.__doc__
    assert func.__doc__.strip()


@pytest.mark.parametrize(
    ("func", "args", "kwargs"),
    [
        (git_ops.run_git_command, (["status"],), {}),
        (git_ops.get_recent_commits, (), {}),
        (git_ops.get_staged_diff, (), {}),
        (git_ops.get_changed_files, (), {}),
        (git_ops.get_diff_stats, (), {}),
        (git_ops.clone_remote_repository, ("https://example.com/repo.git",), {}),
        (git_ops.prepare_repository, (), {}),
        (git_ops.cleanup_repository, ("/tmp/repo",), {}),
    ],
)
def test_stubbed_git_ops_functions_return_none(func, args, kwargs):
    """Current stub implementations should remain safe no-ops until filled in."""
    assert func(*args, **kwargs) is None
