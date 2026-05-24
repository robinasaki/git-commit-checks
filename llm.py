"""LLM helpers for commit analysis and commit-message suggestions."""

import json
import os
from pathlib import Path
from urllib import error, request

MODEL_NAME = "gpt-5-nano"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
SYSTEM_PROMPT = (
    "You are an AI assistant that critiques Git commit messages and suggests clear, "
    "specific, and well-structured alternatives. Always respond with valid JSON only."
)


def load_api_key(env_path=".env", key_name="API_KEY"):
    """Load the API key from environment variables or a local .env file."""
    env_value = os.getenv(key_name)
    if env_value:
        return env_value

    env_file = Path(env_path)
    if not env_file.exists():
        raise RuntimeError(f"Missing environment file: {env_file}")

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#") or "=" not in stripped_line:
            continue

        current_key, current_value = stripped_line.split("=", maxsplit=1)
        if current_key.strip() == key_name:
            return current_value.strip().strip('"').strip("'")

    raise RuntimeError(f"Missing {key_name} in {env_file}")


def get_model_name():
    """Return the fixed model name used by this project."""
    return MODEL_NAME


def build_analysis_prompt(commits):
    """Build the prompt used to critique existing commit history."""
    commit_lines = []
    for index, commit in enumerate(commits, start=1):
        subject = commit.get("subject", "")
        body = commit.get("body", "")
        message = subject if not body else f"{subject}\n{body}"
        commit_lines.append(f"Commit {index}:\n{message}")

    joined_commits = "\n\n".join(commit_lines) if commit_lines else "No commits provided."
    return (
        "Analyze these commit messages and return JSON with the keys "
        "`weak_commits`, `strong_commits`, and `stats`. "
        "Each weak commit should include `commit`, `score`, `issue`, and `better`. "
        "Each strong commit should include `commit`, `score`, and `why_its_good`. "
        "The `stats` object should include `average_score`, `vague_commits`, "
        "`vague_percentage`, `one_word_commits`, and `one_word_percentage`.\n\n"
        f"{joined_commits}"
    )


def build_write_prompt(diff_text, changed_files=None, diff_stats=None):
    """Build the prompt used to suggest a commit message for staged changes."""
    changed_files = changed_files or []
    diff_stats = diff_stats or {}

    files_section = "\n".join(f"- {file_path}" for file_path in changed_files) or "- None"
    stats_section = (
        f"Files changed: {diff_stats.get('files_changed', 0)}\n"
        f"Insertions: {diff_stats.get('insertions', 0)}\n"
        f"Deletions: {diff_stats.get('deletions', 0)}"
    )

    return (
        "Review the staged changes and suggest a clear commit message. "
        "Return JSON with the keys `changes_detected`, `title`, and `bullets`. "
        "`changes_detected` should be a short list of high-level changes. "
        "`title` should be a concise commit title. `bullets` should be optional supporting bullets.\n\n"
        f"Changed files:\n{files_section}\n\n"
        f"Diff stats:\n{stats_section}\n\n"
        f"Staged diff:\n{diff_text}"
    )


def build_messages(user_prompt, system_prompt=SYSTEM_PROMPT):
    """Build the message list that will be sent to the LLM provider."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_request_payload(user_prompt, system_prompt=SYSTEM_PROMPT, model=MODEL_NAME):
    """Build a provider-agnostic chat payload for the fixed model."""
    return {
        "model": model,
        "messages": build_messages(user_prompt=user_prompt, system_prompt=system_prompt),
    }


def request_llm_completion(payload, api_key):
    """Send the request payload to OpenAI and return the generated text response."""
    openai_payload = {
        "model": payload["model"],
        "messages": payload["messages"],
    }
    raw_request = request.Request(
        url=OPENAI_API_URL,
        data=json.dumps(openai_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(raw_request) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed: {error_body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    parsed_response = json.loads(response_body)
    choices = parsed_response.get("choices", [])
    if not choices:
        raise RuntimeError("OpenAI response did not include any choices.")

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not content:
        raise RuntimeError("OpenAI response did not include any message content.")

    return content.strip()


def parse_json_response(response_text):
    """Parse a JSON string returned by the LLM."""
    cleaned_text = response_text.strip()
    if cleaned_text.startswith("```"):
        cleaned_text = cleaned_text.strip("`")
        if cleaned_text.startswith("json"):
            cleaned_text = cleaned_text[4:].strip()

    if cleaned_text and cleaned_text[0] not in "[{":
        object_start = cleaned_text.find("{")
        array_start = cleaned_text.find("[")
        valid_starts = [index for index in (object_start, array_start) if index != -1]
        if valid_starts:
            cleaned_text = cleaned_text[min(valid_starts):]

    if cleaned_text.startswith("{") and "}" in cleaned_text:
        cleaned_text = cleaned_text[: cleaned_text.rfind("}") + 1]
    elif cleaned_text.startswith("[") and "]" in cleaned_text:
        cleaned_text = cleaned_text[: cleaned_text.rfind("]") + 1]

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as error:
        raise ValueError("LLM response was not valid JSON.") from error


def request_json(prompt, api_key=None):
    """Send a prompt to the fixed model and parse the JSON response."""
    resolved_api_key = api_key or load_api_key()
    payload = build_request_payload(prompt)
    response_text = request_llm_completion(payload, resolved_api_key)
    return parse_json_response(response_text)


def analyze_commits(commits, api_key=None):
    """Prepare and send a commit-history analysis request."""
    return request_json(build_analysis_prompt(commits), api_key=api_key)


def suggest_commit_message(diff_text, changed_files=None, diff_stats=None, api_key=None):
    """Prepare and send a staged-diff request for a commit message suggestion."""
    return request_json(
        build_write_prompt(
            diff_text=diff_text,
            changed_files=changed_files,
            diff_stats=diff_stats,
        ),
        api_key=api_key,
    )
