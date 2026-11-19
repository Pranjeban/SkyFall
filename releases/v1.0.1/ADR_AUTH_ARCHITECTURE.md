# ADR — Authentication Architecture for SKYFALL v1.0.1

**Status:** Accepted (2026-11-19)
**Decision:** Keep isolated Azure CLI profiles (no manual client ID). Document deviation from spec's MSAL requirement.

## Context
The v1.0.1 specification document (`Images/V.1..0.1.md`, Module 4) names MSAL as the Microsoft identity/token component. The current implementation (`skyfall_cloud/powerplatform_accounts.py`, `skyfall_mcp/tools/accounts.py`) uses isolated Azure CLI profiles with browser sign-in and short-lived tokens, requiring no user-supplied client ID.

The user has explicitly stated they will not enter a client ID and prefers the Azure CLI path.

## Decision
Retain the isolated Azure CLI profile approach for v1.0.1. Do not migrate to MSAL in this release.

## Rationale
- User preference and prior approval (collaboration memory 2026-11-17).
- Avoids app registration burden and manual client ID entry.
- Existing implementation is working and tested (account tests pass).
- MSAL migration would invalidate existing profiles/token caches (backward-compat risk).

## Consequences
- Spec's MSAL requirement is not met in v1.0.1; documented as accepted deviation.
- Token refresh relies on Azure CLI cache; health checks limited to CLI availability.
- Re-evaluate MSAL for a future release if multi-tenant scope validation or least-privilege recommendations require it.

## Related
- `skyfall_cloud/powerplatform_accounts.py`
- `skyfall_mcp/tools/accounts.py`
- `releases/v1.0.1/README_SKYFALL_V1_0_1.md`
