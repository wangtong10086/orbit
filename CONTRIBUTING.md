# Contributing

Thanks for considering a contribution to ORBIT.

## Before You Start

- Read [README.md](README.md) for the project overview and the primary documented
  workflow.
- Read [docs/getting-started.md](docs/getting-started.md) if your change affects
  the first-run experience.
- Read [docs/testing.md](docs/testing.md) and
  [docs/test-runbook.md](docs/test-runbook.md) before changing runtime-facing
  behavior.

## Development Setup

ORBIT requires Python `>=3.11`.

Recommended setup:

```bash
uv venv
source .venv/bin/activate
cp .env.example .env
uv pip install -e ".[all]"
```

Development docs assume `uv` is the default way to manage Python environments
for this repository.

## Project Documentation Policy

- User-facing docs are English-first.
- The primary documented path is local `control` plus Targon execution.
- If you add or change an example, state whether it is:
  - `recommended + validated`
  - `documented but secondary`
- Do not present a code path as the default user workflow unless it has matching
  validation evidence.

## Pull Request Expectations

For most changes, include:

- a clear summary of what changed
- the user-facing impact
- the commands you ran to verify the change
- documentation updates when behavior or recommended usage changed

## Testing

Minimum checks for documentation-focused changes:

```bash
python3 -m orbit --help
python3 -m orbit control --help
python3 -m orbit worker --help
python3 -m orbit data --help
python3 -m orbit remote --help
python3 -m orbit monitor --help
```

Common broader regression commands:

```bash
pytest -q tests -q
pytest -q tests/test_compute.py tests/test_control.py tests/test_data_cli.py tests/test_execution.py -q
```

When you change runtime-facing behavior, also review:

- [docs/testing.md](docs/testing.md)
- [docs/test-runbook.md](docs/test-runbook.md)

## Documentation Changes

Update docs when you change:

- command behavior
- environment requirements
- recommended workflows
- support maturity or validation status

If you add archive or research material, label it clearly so it does not look
like the primary user-facing path.
