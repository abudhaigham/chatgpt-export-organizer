# Changelog

## 1.3.0 - Unreleased

- Add a controlled export inbox with separate processed and rejected archive folders.
- Validate every ZIP member before import and quarantine incomplete archives with a JSON report.
- Prevent completed export archives from being imported twice by recording their SHA-256 digest.
- Add a local Arabic macOS desktop interface for validation, import, processing, and opening results.
- Add a PyInstaller build helper for `ChatGPT Export Organizer.app`.

All notable changes are documented here. This project follows Semantic Versioning.

## [1.2.0] - 2026-08-26

### Changed

- Conversation folders, JSON files, and PDFs now use human-readable ChatGPT titles
  without internal conversation UUIDs.
- Repeated titles receive readable `(2)`, `(3)`, and later suffixes.
- Conversations are placed under `محادثات بلا مشروع` because the current ChatGPT
  export format does not provide a reliable conversation-to-project relationship.
- Conversation IDs remain preserved in extracted JSON and CSV audit reports.

## [1.1.0] - 2026-08-15

### Added

- Managed imports from ChatGPT export ZIP archives or extracted folders.
- A designated workspace with unique, timestamped import directories.
- Separate protected `source/` snapshots and generated `results/` directories.
- Import manifests containing provenance, layout, version, and ZIP checksum details.
- `LATEST_IMPORT.txt` for quickly locating the newest managed import.
- Automatic discovery of exports contained inside a ZIP wrapper directory.

### Security

- ZIP path-traversal and symbolic-link protection.
- Rename and move operations are prohibited in managed-import mode.
- Repeated imports never overwrite or alter earlier import directories.

## [1.0.0] - 2026-08-07

### Added

- Conversation-aware `.dat` asset mapping.
- CSV audit reporting.
- Safe filename-prefix preview and opt-in rename mode.
- Copy-by-default grouping with explicit move mode.
- Original filename and extension restoration.
- Per-conversation JSON extraction.
- Arabic/English PDF generation with structural validation.
- Compatibility fallback for font-sensitive export content.
- Resumable chat export and per-chat failure reporting.
- Privacy safeguards, synthetic examples, tests, and CI.
