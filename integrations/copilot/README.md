# SKYFALL Copilot integration

The desktop app connects to the locally authenticated Copilot CLI using the pinned `github-copilot-sdk` package.

This release is chat-only. It registers no SKYFALL tools or MCP servers and rejects tool permission requests.

Conversation sessions use stable session IDs. The Copilot SDK stores resumable session transcripts in its own Copilot session-state directory. SKYFALL separately stores the user-visible conversation index and transcript in its local SQLite database.
