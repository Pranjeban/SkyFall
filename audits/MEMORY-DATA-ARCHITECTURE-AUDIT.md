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

---

## 8. Phase 3 full re-audit addendum (2026-11-20) — prior content preserved above

**Agents:** `developer` (memory lifecycle and transactions), `researcher` (Data_Memory/docs, schemas, consumers), `security-auditor` (**failed** provider free-usage quota), `reviewer` (fallback sensitive-data review, different configured model). Orchestrator independently verified git tracking/ignore rules and read-only DB metadata. No source, database, backup or release file was modified.

**Evidence limits:** the live `%LOCALAPPDATA%\SKYFALL\data\` directory does not exist in this environment; live `skyfall.db` and `workspace_index.db` schemas are therefore evidenced from source, not from live files. `Data_Memory/skyfall_memory.sqlite3` was inspected only via Python `sqlite3` immutable/read-only URI; no content rows with private text were reproduced.

### 8.1 Actual data lifecycle

`User interaction → MainWindow._submit_to_copilot (main_window.py:2919) → ConversationStore.add_message (:200-246, validated/transactional) → skyfall.db → get_messages ORDER BY id ASC (:248-269) for UI rendering → CopilotWorker resume_session/create_session (:234-254, :361-388) using copilot_session_id → Copilot SDK transcript (external) → assistant response persisted with status (:3054-3085).`

There is **no** SQLite→SDK context push: only the new prompt is sent (`copilot_service.py:430-431`); prior context is reconstructed by the SDK from its own transcript. `get_messages` feeds the UI only (`main_window.py:3266-3271`).

### 8.2 Schemas and ownership

| Store | Owner | Schema / controls (evidence) |
|---|---|---|
| `%LOCALAPPDATA%\SKYFALL\data\skyfall.db` | `memory/conversation_store.py:45-53` | `conversations(id PK, title, copilot_session_id UNIQUE, created_at, updated_at, sdk_session_initialized)`, `messages(id AUTOINCREMENT PK, conversation_id FK ON DELETE CASCADE, role CHECK, content, status, created_at)`, `app_state(key PK, value)`; indexes `idx_messages_conversation_id_id`, `idx_conversations_updated_at`; WAL, `foreign_keys=ON`, `busy_timeout=20000`; per-call connection, RLock in working tree |
| `%LOCALAPPDATA%\SKYFALL\data\workspace_index.db` | `skyfall_workspace/manager.py:131-138` | `workspaces`, `workspace_files` (FK cascade, `UNIQUE(workspace_id, relative_path)`); indexes `idx_workspace_files_name`, `idx_workspace_files_workspace`; WAL, busy timeout, uncommitted RLock |
| `Data_Memory/skyfall_memory.sqlite3` | No runtime owner; `analyze_db.py:3` only | `conversations(conversation_id PK, title, started_at, source, notes)`, `messages(message_id AUTOINCREMENT PK, conversation_id FK CASCADE, sequence_no, speaker CHECK, content, source_kind, UNIQUE(conversation_id,sequence_no))`, `memory_documents(document_id PK AUTOINCREMENT, path UNIQUE, document_type, content, updated_at)`, `assets(asset_id PK AUTOINCREMENT, relative_path UNIQUE, file_name, media_type, sha256, byte_size, description)`, `metadata(key PK, value)`; index `idx_messages_conversation_sequence`; 6 FTS triggers; FTS5 `messages_fts`/`memory_fts` + 8 shadow tables; metadata keys `schema_version`, `canonical_requested_path`; journal mode delete, not WAL |
| `%LOCALAPPDATA%\SKYFALL\azure_profiles\profiles.json` / `...\powerplatform\profiles.json` | `azure_profiles.py:88-90` / `powerplatform_accounts.py:39-49` | JSON registries, temp+`os.replace`, no file locking; token caches delegated to Azure CLI/MSAL |
| `database/` | None | Empty; `.gitignore:8-9` ignores `database/*.db` and `database/*.sqlite*` |

Read-only counts for the orphan DB: **28 schema objects**, 1 conversation, 35 messages, 9 memory documents, 2 assets, 2 metadata rows. Its schema is incompatible with the live store (`speaker`/`sequence_no` vs `copilot_session_id`/`sdk_session_initialized`), so it is a separate lineage, not a migrated store.

### 8.3 Consumer tracing

- `ConversationStore`: `app/desktop/main_window.py:44,423-426,558-562,2919,3054,3068-3085,3120-3220,3266-3271`; tests `tests/unit/test_conversation_store.py` (8 tests).
- `WorkspaceManager`: `main_window.py:424`, `skyfall_workspace/worker.py:20`, `skyfall_mcp/tools/workspace.py:12`, `scripts/test_mcp_server.py:464-466`; tests use temp DBs.
- `Data_Memory` DB: zero runtime references at HEAD and `origin/v0.9.2` (`git grep "Data_Memory" -- "*.py"`); only untracked `analyze_db.py:3` opens it, with a **write-capable** plain connection.
- Five `ConversationStore` methods have zero callers and zero tests: `update_conversation_title:310`, `delete_message:318`, `search_conversations:327`, `export_conversation_markdown:345`, `backup_database:362`.

### 8.4 Markdown authority and duplication

The four `Data_Memory` Markdown files are hand-maintained, not generated: `README.md` (19-line index and update protocol), `CHAT_HISTORY.md` (116-line curated continuity log), `CHAT_TRANSCRIPT.md` (189-line verbatim user turns plus assistant summaries), `SKYFALL_COLLABORATION_MEMORY.md` (118-line durable goals/issue register). They are authoritative for **intent**; the SQLite DB is a parallel structured snapshot. Records are duplicated (`memory_documents.content` holds Markdown copies; message turns also live in `messages`), and prior verification found stale duplicate rows and 2 dangling assets. All five `Data_Memory` files are **git-tracked** (verified `git ls-files`) and no `.gitignore` rule protects them.

### 8.5 Direct answers to the Phase 3 questions

| # | Question | Answer (evidence above) |
|---|---|---|
| 1 | Which DB stores conversation history? | Live `skyfall.db`; `Data_Memory` holds one imported archival thread |
| 2 | Is `Data_Memory/skyfall_memory.sqlite3` actively used? | No runtime consumer; only untracked `analyze_db.py:3` |
| 3 | Are there multiple SQLite databases? | Yes: `skyfall.db`, `workspace_index.db`, orphan `skyfall_memory.sqlite3`; only the orphan is in-repo |
| 4 | Markdown authoritative or generated? | Hand-maintained, authoritative for intent; not generated |
| 5 | Are records duplicated? | Yes — Markdown content in `memory_documents`, turns in `messages`; drift observed |
| 6 | How is context assembled? | Copilot SDK `resume_session` by `copilot_session_id`; SQLite is display/index only |
| 7 | Long conversation history handling? | `list_conversations` capped 500; `get_messages` has no pagination/truncation; SDK transcript external |
| 8 | Is memory searchable? | UI client-side filter only; store `LIKE` search dormant; Data_Memory FTS5 unused at runtime |
| 9 | Are there indexes? | Yes — two in each live store, plus orphan FTS/auto indexes |
| 10 | Projects/sessions/conversations distinguished? | `workspaces` = approved roots; `conversations.id` = chat UUID; `copilot_session_id` = SDK session; no project entity |
| 11 | Migrations implemented? | No — `CREATE TABLE IF NOT EXISTS` only; orphan metadata `schema_version=1` |
| 12 | Backup/restoration supported? | `backup_database` unwired; no restore or workspace/orphan backup |
| 13 | Import/export supported? | Export returns a Markdown string with zero callers; no import path |
| 14 | Concurrency issues possible? | Yes — single-process RLock, multi-instance `WorkspaceManager`, unlocked JSON registries |
| 15 | Can crashes leave partial writes? | `add_message` is transactional, but a crash between user and assistant persist diverges from SDK; WAL sidecars may retain data |
| 16 | Connections managed safely? | Per-call contextmanager with commit/rollback/finally close; FK pragma per connection |
| 17 | Is deletion consistent? | Local cascade + `app_state` clear; SDK transcript and Markdown/SQLite copies are not deleted |
| 18 | Are identifiers preserved? | UUID conversation IDs, `skyfall-*` session IDs, autoincrement message IDs; no migration renumbering |
| 19 | Clear separation of history/persistent/project/session memory? | Partial — four distinct stores, but Data_Memory duplicates content, no project entity, and SDK transcripts are external |

### 8.6 Transaction/crash/concurrency findings

`add_message` wraps message insert, first-user title derivation and `app_state` upsert in one DEFERRED transaction with rollback on exception (`conversation_store.py:59-76,214-246`). Risks: `sdk_session_initialized=True` is set even on failed/interrupted responses (`main_window.py:3068-3085`), making an inconsistent session resumable; deletion leaves the SDK transcript orphaned and the replacement conversation starts with `resume=False`; `get_or_create_active_conversation` silently falls back to the latest conversation when the active row is missing; locking is single-process only.

### 8.7 Security posture (fallback reviewer, read-only)

**Closed:** M-04 extended redaction (`command_runner.py:50-56`, applied at `:112-113,125-126`; CLI error `azure_profiles.py:283`); M-02 high-entropy + SaaS-prefix detection (`analyzer.py:57-129`, with `sensitive_flag` exclusions in `manager.py:419,448,575,644`); M-05 profile deletion removes isolated Azure CLI dir (`azure_profiles.py:192-204`); `SKYFALL_TEST_MODE` guards confirmed (`tools/accounts.py:70,171`, `azure_profiles.py:255-256`, `command_runner.py:78-84`, `azure_resources.py:349`, `powerplatform_resources.py:247`); export now includes status/session metadata (`conversation_store.py:352,356`).

**Still open:** **High** H-01 plaintext conversation storage (`conversation_store.py:45-48,222-229`); H-02 export emits raw `message.content` without redaction (`:358`, zero callers). **Medium** M-01 no persist-time secret scanning; M-03 unlocked profile JSON registries; M-06 all five `Data_Memory` files git-tracked with no ignore rule; `backup_database` writes an unencrypted, caller-supplied destination without validation. **Low** WAL sidecars, tenant hints/config paths in metadata, secret-named JSON keys retained in analyzer headings; untracked `analyze_db.py:3,16-22` prints raw Data_Memory rows to stdout. Remediations are regex/entropy heuristics with thresholds and are not enforced controls.

**No destructive action taken.** Any future ignore rule, scrubbing, encryption or deletion of `Data_Memory` artifacts requires explicit user approval and preservation of historical records.

### 8.8 Exit assessment

Data ownership, schemas, consumers, lifecycle, context reconstruction, duplication, transaction safety and security posture are now evidenced, with explicit limits where live DB files are unavailable. Phase 3 exit criteria are met. **Approval is required before Phase 4.**

---

## Phase 8 re-verification (2026-11-20)

### 8.9 Descriptive-only clarification (D6)

- The §8.5 Q1 answer describing `Data_Memory/skyfall_memory.sqlite3` as an "imported archival thread" is **DESCRIPTIVE of observed lineage only, NOT a decision on D6** (live vs archival). D6 remains **PENDING**. Original line preserved verbatim.

### 8.10 Phase 8 re-verification evidence (2026-11-20)

- Prior Phase 8 fixes present: `skyfall_workspace/manager.py:11,137,144-158` (threading.RLock; `_connection()` uses `with self._lock:` at :146); `memory/conversation_store.py:345-360` (`export_conversation_markdown` includes `copilot_session_id:351`, `sdk_session_initialized:352`, message status :356).
- Orphan DB has ZERO runtime `.py` consumers (only standalone `analyze_db.py:3`); schema-incompatible; git-tracked. Runtime DBs: `conversation_store.py:61,367,369`, `manager.py:147`. No schema_version/migration framework; bootstrap uses `CREATE TABLE IF NOT EXISTS` (`conversation_store.py:83,95,109`; `manager.py:164,180`).
- Integrity evidence (read-only immutable URI, NO writes): SHA-256 `44C322A00DD2B08B4001E5CB80E16176FF4FA0611CF76B682A0F564AEF3A5B01`, 434,176 B, `PRAGMA integrity_check = ok`, 28 sqlite_master objects; counts conversations=1, messages=35, memory_documents=9, assets=2, metadata=2. Full suite: 100 passed/53 subtests in 1.81s.
- Live `%LOCALAPPDATA%\SKYFALL\data\` ABSENT → no migration/back-up/copy test possible.

**Addendum compliance:** no source/config/DB/backup/release changed; no pending decision resolved; limitations recorded honestly; migration tests NOT claimed as passed.