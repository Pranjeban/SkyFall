# Data_Memory

Local continuity folder for SKYFALL planning, conversation history, and issue evidence.

If the user says **"pull the memory from Data_Memory"**, read these files first:

1. [V1.0.1-RESUMPTION-MEMORY.md](V1.0.1-RESUMPTION-MEMORY.md) — **read this FIRST for phase-gated v1.0.1 work**: exact phase state, copy/paste resumption prompt, verified facts, outstanding decisions, deliverable inventory.
2. [SKYFALL_COLLABORATION_MEMORY.md](SKYFALL_COLLABORATION_MEMORY.md) — durable product goals, priorities, and implementation status.
3. [CHAT_HISTORY.md](CHAT_HISTORY.md) — conversation summary and resumption instructions.
4. [CHAT_TRANSCRIPT.md](CHAT_TRANSCRIPT.md) — verbatim user messages available from this thread and an assistant work summary.

Screenshots are in [Images](Images/).

Requested canonical path: `C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Data_Memory`. Current workspace restriction allows writing only inside the nested `Skyfall` project, so this working copy is at `C:\Users\pranj\OneDrive\Documents\Skyfall(1)\Skyfall\Data_Memory`. The linked ChatGPT pages are references only; their contents were not available to transcribe.
# SQLite memory store

Structured memory is stored in `skyfall_memory.sqlite3` alongside the readable Markdown files. Tables include `conversations`, `messages`, `memory_documents`, `assets`, and `metadata`; full-text search tables index messages and memory documents. Images remain as files under `Images/`; their SHA-256, type, size, path, and description are registered in SQLite.

The current imported history covers the user turns available in this project thread and the assistant implementation summary. It does not contain the inaccessible contents of the supplied ChatGPT URLs. When memory changes, update the Markdown files and corresponding SQLite records together. Keep Markdown as the human-readable backup.

