# SKYFALL Memory & Data Architecture Audit

## 1. Storage locations

### A. `Data_Memory/` (data-only, not code)
- `CHAT_HISTORY.md` (12,013 bytes) — conversation summary + resumption instructions.
- `CHAT_TRANSCRIPT.md` (13,620 bytes) — verbatim user messages + assistant work summary.
- `README.md` (1,678 bytes) — describes folder; SQLite tables.
- `SKYFALL_COLLABORATION_MEMORY.md` (15,401 bytes) — durable product goals, priorities, status, screenshot index, update protocol.
- `skyfall_memory.sqlite3` (434,176 bytes) — structured memory DB.
- `Images/` — issue screenshots (two deleted in working tree).

### B. `memory/` (code module)
- `memory/conversation_store.py` — conversation/message persistence (SQLite-backed). Active, imported by `app.desktop.main_window`.
- `memory/__init__.py`.

### C. `database/`
- No top-level `database/` directory in current repo. DB ownership is split across `memory/` and `Data_Memory/` and internal stores in `skyfall_workspace`/`skyfall_cloud`.

## 2. SQLite schema (`Data_Memory/skyfall_memory.sqlite3`)
Tables: `conversations`, `messages`, `memory_documents`, `assets`, `metadata`, plus FTS5 virtual tables `messages_fts`, `memory_fts` and supporting `_data/_idx/_docsize/_config` tables. Triggers maintain FTS on insert/update/delete.

- `conversations(conversation_id PK, title, started_at, source, notes)`
- `messages(message_id PK AUTOINCREMENT, conversation_id FK CASCADE, sequence_no, speaker CHECK in (user,assistant,system), content, source_kind; UNIQUE(conversation_id, sequence_no))`
- `memory_documents(document_id PK AUTOINCREMENT, path UNIQUE, document_type, content, updated_at)`
- `assets(asset_id PK AUTOINCREMENT, relative_path UNIQUE, file_name, media_type, sha256, byte_size, description)`
- `metadata(key PK, value)` — `schema_version=1`, `canonical_requested_path=...`
- Index: `idx_messages_conversation_sequence ON messages(conversation_id, sequence_no)`

## 3. Current data counts
- conversations: 1 (`skyfall-thread-available-history`)
- messages: 35
- memory_documents: 9
- assets: 2
- metadata: 2
- FTS tables populated and consistent with base tables.

## 4. Data flow (actual)
User interaction -> `app.desktop.main_window` -> `memory.conversation_store` (ConversationStore) -> SQLite (`Data_Memory/skyfall_memory.sqlite3` for imported history; app-local store for live chat) -> retrieval/search -> context assembly -> Copilot worker.

Note: live chat history is indexed in `memory/conversation_store.py` (per PROJECT_DIRECTION). Copilot SDK session transcripts stored separately. Data_Memory DB is the imported/historical record.

## 5. Key questions answered
1. Conversation history stored in multiple locations: yes (live store via memory module + Data_Memory imported record + Copilot SDK transcripts).
2. `Data_Memory/skyfall_memory.sqlite3` actively used: as imported/historical record; README documents it. Not the live app DB necessarily.
3. Other SQLite DB: yes, the live conversation store (location managed by `memory/conversation_store.py`).
4. Markdown generated from DB: Markdown is the human-readable backup; DB holds structured records. They are kept in sync manually per README update protocol.
5. Markdown authoritative or derived: hybrid — human-readable backup; DB is structured source for search.
6. Duplicated memory records: possible between live store and imported Data_Memory DB; not consolidated.
7. Context assembly: via ConversationStore retrieval + Copilot service.
8. Long conversations: not explicitly handled beyond SQLite storage; no pagination/summarization evident.
9. Searchable: yes, via FTS5 on messages and memory_documents.
10. Indexes: `idx_messages_conversation_sequence`; FTS virtual tables.
11. Project/workspace association: no FK to project/workspace in schema.
12. Migrations: `schema_version` metadata = 1; no migration framework evident beyond that.
13. Backup/restore: none automated; Data_Memory itself is the backup artifact.
14. Export/import: Markdown export implied; no formal import path.
15. Preserve old records on upgrade: CASCADE delete on messages; conversations PK preserved.
16. Concurrency: single SQLite file; connection handling in conversation_store to verify.
17. Crash partial data: transactions usage to verify in conversation_store.
18. Connection closure: to verify.
19. Safe deletion: conversation delete implemented; empty drafts filtered from list (per collaboration memory fix).
20. Distinction conversation vs persistent vs project vs session: partially; schema lacks project association.

## 6. Risks
- Split ownership between `memory/` and `Data_Memory/` with manual sync.
- No automated backup/migration framework.
- `.venv` broken (points to missing interpreter) blocks test execution.
- Two deleted screenshot files in working tree (Data_Memory/Images).

## 7. Phase 3 Re-verification Addendum (2026-11-20)

### Correction to prior audit
- §4 of the existing doc is INCORRECT: live chat does NOT write to `Data_Memory/skyfall_memory.sqlite3`. The active runtime conversation store is `memory/conversation_store.py`, whose DB is `%LOCALAPPDATA%\SKYFALL\data\skyfall.db`. `Data_Memory/skyfall_memory.sqlite3` is an orphaned knowledge/imported-history artifact (zero `*.py` references). The §4 sentence claiming live writes to the Data_Memory DB must be read as superseded by this addendum.

### 7.1 Active runtime conversation store (`memory/conversation_store.py`)
- DB path: `%LOCALAPPDATA%\SKYFALL\data\skyfall.db` (NOT `Data_Memory/skyfall_memory.sqlite3`).
- Schema: `conversations(id TEXT PK, title, copilot_session_id UNIQUE, created_at, updated_at, sdk_session_initialized)`; `messages(id INTEGER PK AUTOINCREMENT, conversation_id FK ON DELETE CASCADE, role CHECK, content, status DEFAULT 'complete', created_at)`; `app_state(key PK, value)`. 2 indexes. WAL journal mode. `foreign_keys=ON`, `busy_timeout=20000`. Per-call connection behind `RLock`.
- Lifecycle: `create_conversation`, `get_or_create_active_conversation`, `list_conversations` (hides empty drafts via `HAVING COUNT>0`), `add_message` (role/content validation, auto-titles first user msg, transactional), `get_messages` (ORDER BY id ASC), `set_sdk_session_initialized`, `set_active_conversation`, `delete_conversation` (cascade; clears active).
- Five additive methods (lines 310-374) have zero callers/tests: `update_conversation_title`, `delete_message`, `search_conversations` (LIKE), `export_conversation_markdown`, `backup_database` (sqlite3.Connection.backup).
- SDK session transcripts stored separately by Copilot runtime, keyed by `copilot_session_id` (resume at `main_window.py:3189-3192`).

### 7.2 Three distinct databases
1. `skyfall.db` (conversations) — `%LOCALAPPDATA%\SKYFALL\data\`, WAL, RLock.
2. `workspace_index.db` (workspace metadata) — WAL, `busy_timeout=20000`, no RLock (potential race on concurrent scans).
3. `skyfall_memory.sqlite3` (knowledge) — `Data_Memory/`, journal_mode=delete (not WAL). Counts: 1 conversation, 35 messages, 9 memory_documents, 2 assets, 2 metadata. `schema_version=1`, `canonical_requested_path` metadata. Orphaned from runtime code but holds imported thread content.

### 7.3 Memory layering (clearly separated)
- Conversation memory: `skyfall.db`.
- Persistent/project memory: `workspace_index.db` + `Data_Memory/`.
- Session memory: Copilot SDK transcripts (keyed by `copilot_session_id`).
Identifiers preserved: UUID conversation ids; `copilot_session_id = "skyfall-{hex}"`; message autoincrement.

### 7.4 Memory-store characteristics
- No pagination/truncation in `get_messages`; `list_conversations` capped at 500.
- `search_conversations` is LIKE (no FTS in app DB); `messages_fts` FTS5 exists only in Data_Memory DB, unused at runtime.
- No migrations ever (`CREATE TABLE IF NOT EXISTS` only); `schema_version` metadata in Data_Memory = 1.
- No import path; `export_conversation_markdown` omits `copilot_session_id`, `sdk_session_initialized`, message status; `backup_database` has no restore counterpart.
- Deletion consistency: FK cascade ON DELETE CASCADE; `active_conversation_id` cleared on delete.

### 7.5 Consumer / path tracing
- `ConversationStore` consumers: `app/desktop/main_window.py` (active GUI), `tests/unit/test_conversation_store.py`. No other importers.
- `Data_Memory/skyfall_memory` references in `*.py`: ZERO — orphan artifact.
- `WorkspaceManager` consumers: `main_window.py:424`, `skyfall_workspace/worker.py:20`, `skyfall_mcp/tools/workspace.py:11`, `scripts/test_mcp_server.py:464`.
- No automated backup/restore/import/export in production code paths (only unused methods).
- SQLite WAL + busy_timeout in both stores; transactions per method; `scan_workspace` deletes+reinserts in one transaction.

### 7.6 Security findings (severity-labeled)
**High**
- H-01: Conversation messages stored in plaintext SQLite (no at-rest encryption). DB path `%LOCALAPPDATA%\SKYFALL\data\skyfall.db`; UI labels it "not app-encrypted" (`main_window.py:2791`).
- H-02: `export_conversation_markdown` emits raw content without redaction.

**Medium**
- M-01: No secret scanning before persisting conversation content (`add_message` stores verbatim).
- M-02: Workspace analyzer secret detection keyword-only (no high-entropy).
- M-03: Profile registries (`azure_profiles.json`, PowerPlatform `profiles.json`) written without file locking (atomic replace only).
- M-04: `redact_sensitive_text` misses `api_key`, `connection_string`, `subscription_key`, etc.
- M-05: PowerPlatform profile removal leaves orphaned Azure CLI config dirs for linked profiles.
- M-06: `Data_Memory/*.md` and `skyfall_memory.sqlite3` contain verbatim user content/paths/links; treat as sensitive; gitignore `*.sqlite*` in `Data_Memory/`.

**Low**
- L-01: WAL sidecars may retain unflushed data.
- L-02: `backup_database` produces unencrypted plaintext copy.
- L-03: Profile metadata exposes tenant hints and config_dir paths.
- L-04: Workspace analyzer JSON top-level keys can include secret-named keys.

**Positive controls:** token delegation to Azure CLI/MSAL (DPAPI/encrypted persistence); no tokens in own registries; `shell=False` argv; `redact_sensitive_text`; next-link host validation; token host allow-list; MCP stripping of `sensitive_flag`/`sha256`; job result secret stripping; test-mode blocking; Excel formula-injection sanitization.

### 7.7 Security remediation priority order
1. H-01 (at-rest encryption / clearly documented plaintext posture).
2. H-02 + M-01 (redaction before persist/export).
3. M-04 (extend redact patterns: api_key, connection_string, subscription_key, …).
4. M-02 (add high-entropy detection to workspace analyzer).
5. M-03 (file locking on profile registries).
6. M-05 (cleanup orphaned Azure CLI config dirs).
7. M-06 (gitignore + scrub Data_Memory artifacts).
8. L-01..L-04 (WAL checkpoint discipline, encrypted backups, metadata minimization).

### Phase 3 exit assessment
Memory and database ownership is now understood (three DBs, three memory layers, clearly separated). Risks and security posture are documented with severity labels and a remediation priority order. Ready for Phase 4.