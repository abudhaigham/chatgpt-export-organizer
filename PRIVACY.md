# Privacy

ChatGPT exports may contain highly sensitive personal, professional, financial,
medical, and account information. Treat an extracted export as confidential.

## Local-only processing

ChatGPT Export Organizer reads and writes local files. The application contains
no telemetry, analytics, remote API calls, or upload functionality.

## Never publish real exports

Do not commit or share:

- `conversations-*.json`
- `.dat` assets
- `chat.html`
- generated PDFs or extracted chat folders
- account or Library metadata
- reports containing real chat titles or conversation IDs

The repository `.gitignore` blocks common root-level export artifacts, but it is
not a substitute for reviewing staged files before every commit.

## Recommended workflow

1. Preserve an untouched backup of the export.
2. Run the tool locally.
3. Keep output outside public repositories.
4. Run `python scripts/privacy_check.py` before publishing source changes.
5. Review `git diff --cached` before every push.
