# User Guide

## 1. Use the managed import workspace (recommended)

The managed workflow accepts either the downloaded ChatGPT ZIP or an already
extracted export folder. It creates a new isolated import every time:

```bash
chatgpt-export-organizer \
  --import-export "/path/to/chatgpt-export.zip" \
  --workspace "$HOME/ChatGPT_Export_Organizer" \
  --quiet --group --restore-originals --export-chats
```

Each managed import contains:

- `source/`: the imported snapshot, preserved unchanged;
- `results/`: CSV reports, grouped assets, restored originals, JSON, and PDFs;
- `import_manifest.json`: import identity, timestamp, paths, version, and ZIP SHA-256;
- `LATEST_IMPORT.txt`: a workspace-level pointer to the newest import.

Running the command again creates another timestamped import. It never merges
with, replaces, or modifies an earlier import. Managed imports reject `--rename`
and `--move` so the protected snapshot remains intact.

## 2. Preserve the source archive

Extract the ChatGPT ZIP and keep an untouched backup. Run the organizer against a
working copy.

## 3. Scan assets

```bash
chatgpt-export-organizer /path/to/export --quiet
```

The report associates each asset with its original filename when known, chat
title, conversation ID, split JSON file, and reference count.

## 4. Group assets

Safe copy mode:

```bash
chatgpt-export-organizer /path/to/export --quiet --group
```

Custom destination:

```bash
chatgpt-export-organizer /path/to/export --quiet \
  --group "/path/to/organized-assets"
```

Move mode changes the source archive and should only be used on a backup:

```bash
chatgpt-export-organizer /path/to/export --quiet --group --move
```

## 5. Restore original names

```bash
chatgpt-export-organizer /path/to/export --quiet \
  --group --restore-originals
```

The `.dat` object contains the original bytes. When metadata records an original
name, the program creates another copy with that filename and extension.

## 6. Extract chats and create PDFs

Install PDF dependencies with `pip install -e ".[pdf]"`, then run:

```bash
chatgpt-export-organizer /path/to/export --quiet --export-chats
```

Export one conversation:

```bash
chatgpt-export-organizer /path/to/export --export-chats \
  --chat-id "conversation-id"
```

Existing valid PDFs are preserved. Re-run the same command to resume an
interrupted batch. Use `--overwrite-chat-exports` only when intentional.

## 7. Read reports

- `ChatGPT_DAT_Chat_Index.csv`: asset mapping and file-operation audit.
- `Extracted_Chats/Chat_Export_Report.csv`: JSON/PDF status for each chat.

Both files use UTF-8 with a byte-order mark for compatibility with Microsoft
Excel.

## Limitations

- PDFs reproduce the active user-assistant branch, while extracted JSON preserves
  the complete conversation object.
- Attachments are referenced but not embedded in PDFs.
- Original names are available only when export metadata records them.
- Export formats may evolve; please report incompatible synthetic examples.
