# git-commit-checks
A short Python program to analyze git logs.

## Assumptions
1. We use a single-process CLI architecture.
## Modules
### `cli.py`
The main entrypoint. Parses arguments and coordinates flow.

Arguments:
- `--analyze`
- `--write`
- `--url`

### `git_ops.py`
All git-related logics, including:
- Get recent commits
- Read staged diff
- Get changed files / stats

### `llm.py`
All LLM-related logics, including:
- Load API key from `.env`
- Send prompts to a fixed model
- Return parsed results for commit scoring or suggested messages

## Getting Started
1. Create a new `.env`. Define the `API_KEY` magic word:
```txt
API_KEY="example_123123_hello_world"
```

2. Install the corresponding dependencies:
```bash
pip install -r requirements.txt
```

## Testing
To run all the tests at once, use `scripts/run_tests.sh`.
```bash
./scripts/run_tests.sh
```