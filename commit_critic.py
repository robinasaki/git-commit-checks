"""Command-line entrypoint for commit analysis and commit-message suggestions."""

import argparse

import git_ops
import llm

ANALYZE_LIMIT = 50
SECTION_DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


def parse_args(argv=None):
    """Parse command-line arguments for analysis or write mode."""
    parser = argparse.ArgumentParser(description="Analyze commit quality with Gemini.")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze recent commits in the current or remote repository.",
    )
    mode_group.add_argument(
        "--write",
        action="store_true",
        help="Suggest a commit message from staged changes.",
    )
    parser.add_argument(
        "--url",
        help="Optional repository URL to analyze remotely.",
    )
    return parser.parse_args(argv)


def format_commit_message(title, bullets=None):
    """Format a commit title with optional supporting bullets."""
    bullets = bullets or []
    if not bullets:
        return title

    bullet_lines = "\n".join(f"- {bullet}" for bullet in bullets if bullet)
    if not bullet_lines:
        return title

    return f"{title}\n\n{bullet_lines}"


def print_analysis_results(result):
    """Print commit-analysis output in a terminal-friendly format."""
    weak_commits = result.get("weak_commits", [])
    strong_commits = result.get("strong_commits", [])
    stats = result.get("stats", {})

    print("\nAnalyzing last 50 commits...\n")
    print(SECTION_DIVIDER)
    print("💩 COMMITS THAT NEED WORK")
    print(SECTION_DIVIDER)
    print()

    if weak_commits:
        for entry in weak_commits:
            print(f'Commit: "{entry.get("commit", "Unknown commit")}"')
            print(f'Score: {entry.get("score", "?")}/10')
            print(f'Issue: {entry.get("issue", "No issue provided")}')
            print(f'Better: {entry.get("better", "No suggestion provided")}')
            print()
    else:
        print("No weak commits found.\n")

    print(SECTION_DIVIDER)
    print("💎 WELL-WRITTEN COMMITS")
    print(SECTION_DIVIDER)
    print()

    if strong_commits:
        for entry in strong_commits:
            print(f'Commit: "{entry.get("commit", "Unknown commit")}"')
            print(f'Score: {entry.get("score", "?")}/10')
            print(f'Why it\'s good: {entry.get("why_its_good", "No explanation provided")}')
            print()
    else:
        print("No strong commits found.\n")

    print(SECTION_DIVIDER)
    print("📊 YOUR STATS")
    print(SECTION_DIVIDER)
    print(f'Average score: {stats.get("average_score", 0)}/10')
    print(
        f'Vague commits: {stats.get("vague_commits", 0)} '
        f'({stats.get("vague_percentage", 0)}%)'
    )
    print(
        f'One-word commits: {stats.get("one_word_commits", 0)} '
        f'({stats.get("one_word_percentage", 0)}%)'
    )


def print_write_results(result, diff_stats):
    """Print staged-change analysis and the suggested commit message."""
    changes_detected = result.get("changes_detected", [])
    title = result.get("title", "chore: update changes")
    bullets = result.get("bullets", [])
    formatted_message = format_commit_message(title, bullets)

    print(
        "Analyzing staged changes... "
        f'({diff_stats.get("files_changed", 0)} files changed, '
        f'+{diff_stats.get("insertions", 0)} -{diff_stats.get("deletions", 0)})\n'
    )
    print("Changes detected:")
    if changes_detected:
        for item in changes_detected:
            print(f"- {item}")
    else:
        print("- No high-level summary returned")
    print()
    print("Suggested commit message:")
    print(SECTION_DIVIDER)
    print(formatted_message)
    print(SECTION_DIVIDER)

    user_input = input("\nPress Enter to accept, or type your own message:\n> ")
    final_message = user_input.strip() or formatted_message
    print("\nFinal commit message:")
    print(SECTION_DIVIDER)
    print(final_message)
    print(SECTION_DIVIDER)
    return final_message


def run_analyze(url=None):
    """Run analysis mode for the current repository or a remote clone."""
    repo_path = git_ops.prepare_repository(url=url)

    try:
        commits = git_ops.get_recent_commits(repo_path=repo_path, limit=ANALYZE_LIMIT)
        if not commits:
            print("No commits found to analyze.")
            return 1

        result = llm.analyze_commits(commits)
        print_analysis_results(result)
        return 0
    finally:
        git_ops.cleanup_repository(repo_path, original_repo=".")


def run_write():
    """Run interactive commit-message writing for staged changes."""
    diff_text = git_ops.get_staged_diff()
    if not diff_text.strip():
        print("No staged changes found.")
        return 1

    changed_files = git_ops.get_changed_files(staged=True)
    diff_stats = git_ops.get_diff_stats(staged=True)
    result = llm.suggest_commit_message(
        diff_text=diff_text,
        changed_files=changed_files,
        diff_stats=diff_stats,
    )
    final_message = print_write_results(result, diff_stats)
    git_ops.commit_staged_changes(final_message)
    print("\nCommit created successfully.")
    return 0


def main(argv=None):
    """Execute the CLI command requested by the user."""
    args = parse_args(argv)

    if args.write and args.url:
        raise SystemExit("--url is only supported with --analyze.")

    try:
        if args.analyze:
            return run_analyze(url=args.url)
        return run_write()
    except RuntimeError as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
