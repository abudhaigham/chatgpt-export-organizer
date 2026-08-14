# ChatGPT Export Organizer

[![CI](https://github.com/abudhaigham/chatgpt-export-organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/abudhaigham/chatgpt-export-organizer/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A privacy-first command-line utility for turning a raw ChatGPT data export into an
auditable, organized archive.

It maps internal `.dat` assets to conversations, restores original filenames,
groups assets by chat, extracts individual conversation JSON files, and creates
readable bilingual PDFs with resumable batch processing.

> Independent community project. Not affiliated with or endorsed by OpenAI.

## Why this project exists

ChatGPT exports can contain split conversation files and hundreds of binary assets
stored under internal `.dat` names. Locating the conversation associated with an
asset—or producing a readable archive of every chat—otherwise requires repeated
manual JSON searches.

ChatGPT Export Organizer automates that workflow locally. It does not upload your
archive or send its contents to an external service.

## Features

- Scan all `conversations-*.json` parts in one pass.
- Map `.dat` assets to chat titles, IDs, and source JSON files.
- Produce an Excel-compatible UTF-8 CSV audit report.
- Preview safe chat-title filename prefixes before renaming.
- Copy or move assets into chat-named folders.
- Restore known original filenames and extensions.
- Extract every conversation into its own JSON file.
- Render active conversation branches as paginated PDFs.
- Shape Arabic correctly and support mixed Arabic/English content.
- Validate PDFs and retry font-sensitive content with a compatibility fallback.
- Resume interrupted exports without recreating valid outputs.
- Protect against collisions, oversized filenames, and repeated prefixes.
- Import ZIP archives or extracted exports into isolated managed workspaces.
- Preserve every imported source snapshot and every earlier import unchanged.

## Recommended managed workflow

Import an exported ChatGPT ZIP directly into the default designated workspace:

```bash
chatgpt-export-organizer \
  --import-export "/path/to/chatgpt-export.zip" \
  --quiet \
  --group \
  --restore-originals \
  --export-chats
```

The default workspace is `~/ChatGPT_Export_Organizer`. Choose another permanent
location with `--workspace`:

```bash
chatgpt-export-organizer \
  --import-export "/path/to/chatgpt-export.zip" \
  --workspace "/path/to/My ChatGPT Archive" \
  --import-name "August 2026" \
  --quiet --group --restore-originals --export-chats
```

Every execution creates a new directory. The original ZIP, the protected imported
snapshot, and all earlier imports remain unchanged.

## Installation

Clone the repository and install the package:

```bash
git clone https://github.com/abudhaigham/chatgpt-export-organizer.git
cd chatgpt-export-organizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[pdf]"
```

PDF dependencies are optional. Install without `[pdf]` if you only need asset
mapping and grouping.

## Quick start

Change to your extracted ChatGPT export directory, then scan it:

```bash
chatgpt-export-organizer . --quiet
```

The command creates `ChatGPT_DAT_Chat_Index.csv`.

Group assets safely by copying them:

```bash
chatgpt-export-organizer . --quiet --group
```

Restore original filenames in the grouped folders:

```bash
chatgpt-export-organizer . --quiet --group --restore-originals
```

Extract every chat and create readable PDFs:

```bash
chatgpt-export-organizer . --quiet --export-chats
```

## Output structure

```text
ChatGPT_Export_Organizer/
├── LATEST_IMPORT.txt
└── imports/
    ├── 20260815T120000000000Z__chatgpt-export/
    │   ├── import_manifest.json
    │   ├── source/                 # protected imported snapshot
    │   └── results/
    │       ├── ChatGPT_DAT_Chat_Index.csv
    │       ├── Grouped_DAT_Files/
    │       └── Extracted_Chats/
    └── 20260901T120000000000Z__chatgpt-export/
        ├── source/                 # a separate later import
        └── results/

Grouped_DAT_Files/
├── Example Conversation/
│   ├── Example Conversation__file-demo123.dat
│   └── project-notes.pdf
└── _Unmatched/
    └── file-unmatched.dat

Extracted_Chats/
├── Example Conversation__conversation-id/
│   ├── Example Conversation__conversation-id.json
│   └── Example Conversation__conversation-id.pdf
└── Chat_Export_Report.csv
```

## Safety model

Copying is the default grouping behavior. Destructive operations require explicit
flags:

- `--rename` renames matched source `.dat` files.
- `--group --move` relocates source assets instead of copying them.
- `--overwrite-chat-exports` recreates existing extracted JSON and PDFs.

Keep an untouched copy of the original export before using these options.

In managed-import mode, `--rename` and `--move` are rejected. Generated reports,
grouped assets, restored files, and chat PDFs are written only under `results/`.

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Privacy model](PRIVACY.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## Proven scale

The v1.0 workflow was validated on an export containing 1,143 conversations,
12 split conversation files, and 1,334 assets. Those private files and their
contents are not included in this repository.

## License

[MIT](LICENSE) © 2026 Mohammad Alhajri.
