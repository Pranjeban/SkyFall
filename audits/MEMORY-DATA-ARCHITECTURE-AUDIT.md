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
