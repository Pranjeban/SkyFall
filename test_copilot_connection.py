"""SKYFALL Copilot SDK connectivity smoke test.

Designed for a single-user local Windows desktop app using the existing
interactive GitHub Copilot CLI sign-in.

This test:
- Uses the SDK's `copilot-cli` mode so stored Copilot CLI credentials apply.
- Uses the administrator-managed model route `auto`.
- Registers no SKYFALL custom tools or MCP servers.
- Requests a simple text-only response.
- Does not read workspace files, execute PowerShell, or access Azure /
  Power Platform through SKYFALL tools.

Note: `copilot-cli` mode is intended for interactive, single-user applications.
Do not reuse this configuration unchanged for a shared/multi-user server.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

try:
    from copilot import CopilotClient
except ImportError as exc:
    print("ERROR: Copilot SDK is not installed in this Python environment.")
    print("Activate SKYFALL's .venv and install the pinned SDK.")
    print(f"Details: {type(exc).__name__}: {exc}")
    raise SystemExit(2) from exc

PROMPT = (
    "This is a connectivity test for the SKYFALL desktop application. "
    "Do not use tools, access files, or run commands. "
    "Reply with exactly: SKYFALL COPILOT CONNECTION SUCCESSFUL"
)


async def main() -> int:
    copilot_home = Path.home() / ".copilot"

    print("SKYFALL: starting Copilot SDK connection test...")
    print("Mode: copilot-cli (interactive local user)")
    print("Model routing: auto (administrator-managed)")
    print("Authentication: existing signed-in Copilot CLI user")
    print(f"Default Copilot home exists: {copilot_home.exists()}")
    print("Custom COPILOT_HOME: not set by this test")
    print("SKYFALL tools/MCP servers registered: none")

    try:
        # In this local, single-user desktop scenario, use the SDK's
        # interactive CLI mode. Empty mode is for explicit/isolation-based
        # deployments and needs its own storage and explicit auth details.
        async with CopilotClient(mode="copilot-cli") as client:
            async with await client.create_session(
                model="auto",
                available_tools=[],
            ) as session:
                response = await asyncio.wait_for(
                    session.send_and_wait(PROMPT),
                    timeout=120,
                )

                data = getattr(response, "data", None) if response else None
                content = getattr(data, "content", None) if data else None

                if not content:
                    print("ERROR: The session completed without assistant text.")
                    return 1

                print("\nCopilot response:")
                print(content)

                if "SKYFALL COPILOT CONNECTION SUCCESSFUL" in content:
                    print("\nRESULT: PASS - SKYFALL can communicate with Copilot.")
                    return 0

                print("\nRESULT: PARTIAL - A response arrived, but the expected phrase was absent.")
                return 1

    except asyncio.TimeoutError:
        print("ERROR: Copilot response timed out after 120 seconds.")
        print("Check connectivity, Copilot service availability and organization policy.")
        return 1
    except Exception as exc:
        print("ERROR: Copilot SDK connection failed.")
        print(f"Exception: {type(exc).__name__}: {exc}")
        print("No authentication tokens were printed or exported by this test.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
