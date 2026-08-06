# Contributing

Contributions are welcome.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[pdf,dev]"
pytest
ruff check .
ruff format --check .
python scripts/privacy_check.py
```

## Privacy requirements

Use only synthetic fixtures. Pull requests containing real conversation text,
conversation IDs, account data, `.dat` assets, generated PDFs, or exported files
will not be accepted.

## Pull requests

- Add tests for behavioral changes.
- Update documentation and `CHANGELOG.md` when appropriate.
- Keep changes focused and backwards compatible where practical.
- Confirm all quality and privacy checks pass.
