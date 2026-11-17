# SKYFALL v0.7.1 — Microsoft Account Intelligence UX and Sign-in Fixes

## Summary

This patch release addresses the signed-out Azure screen and makes Microsoft profile creation a guided, conversational workflow.

### Azure

- Keeps the Azure profile selector.
- Removes the separate Refresh Subscriptions control; discovery runs on startup, profile selection and after successful authentication.
- Moves account creation into **Manage profiles → Add profile**.
- The creation dialog requires a profile display name and tenant GUID or verified tenant domain.
- **Create & sign in** creates an isolated profile, opens browser-based Microsoft sign-in, and automatically fetches the canonical tenant ID and subscriptions.
- The default Azure CLI profile remains read-only; SKYFALL does not overwrite the user's normal Azure CLI context.
- Normal unauthenticated profiles now display a friendly disconnected state, not the raw `ERROR: Please run 'az login' to setup account.` message.
- Existing profiles with missing tenant hints prompt for the tenant before login.

### Power Platform

- Profile creation asks for a PAC profile name and optional environment name/URL/ID.
- Interactive sign-in launches through PAC CLI. In delegated user sign-in, tenant is derived from the Microsoft account chosen in the browser. The user-flow does not accept a separate tenant ID argument.
- Profile and environment discovery runs after successful sign-in. The environment table displays tenant ID when returned by PAC CLI.
- Because PAC CLI profiles/active profile selection apply to the local PAC CLI installation, SKYFALL presents a warning and requires explicit confirmation before creating a profile from Chat or UI.
- Power Platform Chat login tool includes `confirm_global_profile_activation`; without explicit true confirmation, no profile is created and no login starts.

### Conversational login

- Copilot system instructions require profile name and tenant hint for a new Azure profile.
- The agent tells the user when a browser sign-in should open and checks the background authentication job after the user confirms completion.
- The desktop automatically re-runs the matching read-only discovery after chat-based authentication, so the account page reflects the new profile.

### Safety

- No cloud resource modifications are exposed.
- No PowerShell/Python script execution is exposed.
- No arbitrary shell commands are exposed.
- Azure credentials are held by the isolated Azure CLI profile directory; PAC CLI retains its credential store. SKYFALL profile metadata contains no tokens.

## Browser behavior

For Azure, SKYFALL sets `core.enable_broker_on_windows=false` and `core.login_experience_v2=off` only within the isolated profile's `AZURE_CONFIG_DIR`, then runs `az login --tenant ... --allow-no-subscriptions`. Azure CLI opens the default browser when available; its documented fallback may use device-code login when the browser cannot be opened.

For Power Platform, `pac auth create` opens its normal interactive login experience. The correct account is chosen by the user in the Microsoft sign-in flow.

## Test counts

- Python compileall: passed in build environment.
- Unit tests: 57 passed.
- Windows Qt GUI and real Azure/PAC browser sign-in: must be verified on the user's Windows PC.
- MCP stdio end-to-end smoke test: source updated; the build environment has no network access to install the MCP SDK, so run it in SKYFALL's existing `.venv` on Windows.
