# SKYFALL v0.6 — Workspace Intelligence

## Release objective

Add read-only local workspace discovery to SKYFALL while preserving the working v0.4 conversation store, v0.3 Copilot integration and v0.5 MCP core framework. Correct chat Markdown rendering in the same release.

## Included capabilities

### Desktop

- Workspace Intelligence navigation page.
- Add and remove a specific workspace folder.
- Local background scan of selected or all workspaces.
- Local metadata search and metadata detail dialog.
- Per-workspace explicit Copilot metadata-sharing consent (default OFF).
- Workspace controls are disabled during a running scan to avoid remove/add/consent races.
- Chat messages render Markdown using Qt's document Markdown parser.

### Workspace indexing

- Supported formats: PowerShell, Python, YAML, JSON, Markdown, TOML, INI, CFG, Batch, CMD, SQL, XML, JavaScript, TypeScript, C#, Bicep, Terraform, and Shell.
- Static metadata only: file metadata, names, parameters, functions, classes, import/module names, command identifiers, and structural headings/keys.
- Source contents are read locally to extract structure but are not stored in the index or returned by workspace MCP tools.
- File fingerprints are stored locally only and are omitted from MCP responses.
- Obvious credential files and sensitive directories are skipped.
- Heuristic content-based secret detection flags matching files and excludes them from local search and AI search.
- Symlinks and reparse points are skipped.

### Limits

- Maximum file size: 2 MiB.
- Maximum indexed files per workspace: 20,000.
- Maximum content read per workspace scan: 512 MiB.
- Maximum directory depth: 24.
- MCP search query: 1–200 characters.
- MCP search result count: 1–50.

### MCP tools

The server exposes seven read-only tools: three core tools and four workspace metadata tools. The Copilot session explicitly allow-lists these seven tool IDs and rejects other tool permission requests.

### Database

Workspace metadata is stored in `%LOCALAPPDATA%\SKYFALL\data\workspace_index.db`, separate from the conversation database. The MCP child process receives the same `LOCALAPPDATA` value as the desktop process so both read the same index.

## Security notes

- AI metadata sharing is opt-in per workspace and starts OFF.
- AI-visible metadata is still corporate information; the user must follow employer data-handling policy before opting in.
- Secret detection is heuristic and cannot guarantee the absence of secrets. The UI warns users not to share sensitive folders.
- Workspace metadata is treated as untrusted data by the Copilot system instructions.
- No source-code read tool, arbitrary filesystem tool, shell, PowerShell, cloud or script-execution tool is enabled.

## Validation

Build-environment checks performed for this release:

- Python 3.11 grammar parse for all project Python files.
- 33 unit tests passed.
- End-to-end STDIO MCP smoke test prepared for Windows execution.

The build environment used for packaging did not contain PySide6 or the MCP runtime, so actual Qt rendering and the Windows STDIO subprocess test must be verified on the user's PC after applying the update.
