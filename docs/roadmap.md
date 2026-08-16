# Roadmap

## Complete

- current MyQ OAuth/PKCE login with email and SMS MFA;
- refresh-token persistence and rotation;
- account, hub, and device discovery;
- account-scoped exact target matching;
- redacted status output and private observations;
- guarded open and close commands;
- command-state polling through terminal state;
- live validation of one complete open/close cycle;
- public/private configuration split.

## Next

1. Add structured JSON results for open/close acceptance, transitions, and
   timeout diagnostics.
2. Add configurable polling intervals with conservative lower bounds.
3. Expand sanitized fixtures for safety reversal, offline, rate-limit, and
   token-revocation behavior.
4. Add release automation and signed artifacts after the API stabilizes enough
   for versioned distribution.

## Implementation direction

A future Rust port should preserve the CLI, private config paths, redaction,
JSON contract, and `script/install` entry point. Keep the Python implementation
until the replacement reaches behavioral and safety parity.

## Deliberately out of scope

- toggle commands;
- unauthenticated network services;
- automatic geofence or presence operation;
- storage of account passwords or MFA codes;
- committing OAuth tokens or live observations, even to private repositories;
- bypassing safety sensors, warning delays, or manufacturer controls.
