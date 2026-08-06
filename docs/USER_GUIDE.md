# User Guide

## 1. Preserve the source archive

Extract the ChatGPT ZIP and keep an untouched backup. Run the organizer against a
working copy.

## 2. Scan assets

```bash
chatgpt-export-organizer /path/to/export --quiet
```

The report associates each asset with its original filename when known, chat
title, conversation ID, split JSON file, and reference count.

## 3. Group assets

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

## 4. Restore original names

```bash
chatgpt-export-organizer /path/to/export --quiet \
  --group --restore-originals
```

The `.dat` object contains the original bytes. When metadata records an original
name, the program creates another copy with that filename and extension.

## 5. Extract chats and create PDFs

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

## 6. Read reports

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
