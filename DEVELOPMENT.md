# SKYFALL Development Guide

This document describes the current engineering contract for the SKYFALL
desktop application. It is a living document: update it whenever dependencies,
tooling, module boundaries or verification commands change.

## 1. Scope and non-negotiables

SKYFALL is a modular monolith, not a set of microservices. Part 15 of the v1.1
roadmap remains intentionally skipped; do not introduce a new top-level package
layout or reorganise historical folders.

Preserve the following without explicit approval:

- databases, backups, historical releases and prior reports;
- dormant `backend/api.py` and currently unwired Tier-3 services;
- uncommitted work owned by the user;
- version strings pending D8 (`0.9.2` in the desktop/capability surfaces and
  `1.0.1` in the dormant API);
- resolved decisions D1 and D7, and unresolved decisions D6, D8, D18, D20
  and D21;
- historical tool-count statements in audit and release records.

Never perform destructive Git operations, database writes, backup overwrites or
history rewrites as part of routine cleanup. Keep assistant work uncommitted
unless the user explicitly approves a commit.

## 2. Style contract

Follow PEP 8 with these project rules:

- indent with four spaces, never tabs;
- keep lines at or below 79 characters;
- group imports as standard library, third party, then first party;
- use `snake_case` for variables and functions;
- use `PascalCase` for classes;
- use `ALL_CAPS_WITH_UNDERSCORES` for module constants;
- write module, class and public-function docstrings;
- explain why in comments when the reason is not obvious from the code;
- avoid comments that merely restate the code.

Static settings live in:

- `.flake8` — line length and excluded historical trees;
- `pyproject.toml` — Black, mypy and pytest configuration.

The linters are intentionally not installed in the default runtime. Install the
development tool set explicitly when needed:

```powershell
venv_skyfall\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Run static checks:

```powershell
$py = "venv_skyfall\Scripts\python.exe"
$src = @(
    "app", "integrations", "skyfall_cloud",
    "skyfall_mcp", "skyfall_workspace", "tests"
)
& $py -m flake8 $src
& $py -m black --check $src
& $py -m mypy
```

These tools are configuration-only until installed; do not claim they passed
unless they were actually executed.

## 3. Dependency policy

Dependencies are split by purpose:

| File | Purpose |
| --- | --- |
| `requirements.txt` | Desktop/runtime dependencies |
| `requirements-dev.txt` | Test, lint, format and type-check tools |
| `requirements-optional.txt` | Dormant local-service dependencies |

Rules:

1. Add a dependency only when first-party code imports it or a documented
   compatibility reason exists.
2. Pin only where an external contract was verified. The Copilot SDK is pinned
   to `1.0.34` because its tool-ID behaviour was validated against that build.
3. Prefer conservative compatible ranges for everything else.
4. Never place credentials, tenant IDs, tokens or private feed URLs in
   requirement files.
5. When a dependency changes, update this guide and the durable audit records.

`fastapi` and `uvicorn` are optional because `backend/api.py` guards those
imports and fails with a clear message when the local service is not enabled.

## 4. Design principles

Apply these principles in order:

- **DRY** — keep one implementation per rule; extract shared helpers rather
  than copying validation or redaction logic.
- **KISS** — prefer the simplest solution that preserves behaviour.
- **YAGNI** — do not build future abstractions without a present requirement.
- **Separation of concerns** — keep UI rendering, business logic and data
  access in their existing layers.
- **Configurable and extensible** — prefer the capability catalogue and clear
  interfaces over hard-coded route lists.
- **Fail gracefully** — convert expected failures into actionable payloads;
  redact secrets and sensitive paths before displaying or logging them.

Do not introduce Kubernetes, microservices or a new service boundary to solve
a problem that belongs inside the existing module.

## 5. Dynamic scalability model

Dynamic behaviour should come from registered capability metadata and explicit
interfaces, not from scattered conditionals in the desktop UI.

The intended flow is:

```text
prompt -> capability resolution -> plan -> validation
       -> handler -> result -> history
```

Rules:

1. The capability catalogue is the source of truth for available tools.
2. Modules expose narrow interfaces; callers depend on the interface, not on a
   concrete worker or page.
3. UI code renders results; it does not duplicate cloud or workspace logic.
4. Service logic returns structured payloads; the UI decides how to display
   them.
5. Handlers are registered by capability/tool name instead of being selected
   through long `if`/`elif` chains.
6. Any new dynamic route must preserve read-only defaults and the existing
   approval boundary.

No new top-level package is required to follow this model.

## 6. Error handling and redaction

- Catch specific exceptions where recovery or translation is meaningful.
- Broad `except Exception` is acceptable only at containment boundaries and
  must include a short rationale.
- User-facing failures should include a safe summary and, where useful, an
  actionable next step.
- Never expose tokens, Authorization headers, absolute file paths, UNC paths,
  source content, password material or credential files.
- Reuse existing redaction helpers before adding new ones.

## 7. Testing contract

Authoritative test command:

```powershell
venv_skyfall\Scripts\python.exe -B -m pytest tests/ -q -p no:cacheprovider
```

MCP stdio smoke test:

```powershell
$env:SKYFALL_TEST_MODE = "1"
venv_skyfall\Scripts\python.exe -B scripts\test_mcp_server.py
```

Testing rules:

- add unit tests beside behaviour changes;
- keep UI acceptance tests static and free of Qt imports;
- avoid live tenant, network, GUI or credential-dependent assertions;
- use test mode and isolated temporary databases for integration checks;
- preserve historical test evidence instead of rewriting old counts;
- record the final executed counts in the durable audit records.

## 8. Documentation records

Update these files when a user-visible milestone completes:

- `Data_Memory/V1.0.1-RESUMPTION-MEMORY.md`
- `audits/V1.0.1-PROGRESS-RECORD.md`
- `audits/V1.0.1-IMPLEMENTATION-REPORT.md`

Append new sections. Do not rewrite historical evidence, including earlier tool
counts such as 20, 33 or 34.

## 9. Git hygiene

- Run `git diff --check` before reporting completion.
- Keep unrelated changes out of the same edit.
- Do not reset, rebase, stash, amend or force-push.
- Do not delete historical backups or releases.
- Generated caches and local artifacts are ignored through `.gitignore`;
  tracked historical `.bak` files are deliberately preserved.

## 10. Verification checklist

Before reporting a change as complete:

1. Full unit suite passes.
2. MCP stdio smoke passes when the MCP surface changed.
3. Tool wiring is checked across server, capability catalogue and Copilot.
4. `git diff --check` is clean apart from known line-ending warnings.
5. No database, backup, release, version string or pending decision changed.
6. This guide and the durable audit records reflect the final state.
