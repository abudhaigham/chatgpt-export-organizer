# Synthetic export fixture

This directory models the minimum metadata needed to demonstrate scanning without
containing real user data. `export_manifest.json` lists a zero-byte synthetic asset;
the binary `.dat` file is intentionally absent.

Run from the repository root:

```bash
chatgpt-export-organizer examples/synthetic_export --quiet
```
