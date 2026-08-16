# Repository guidance

## Purpose

`gatectl` is a terminal-first MyQ gate and garage-door inspection and control
tool. Keep authentication, HTTP transport, account/device selection, storage,
and CLI dispatch separate. Treat every physical-access write as safety-sensitive.

## Engineering principles

- Read exact account and device state before performing a write.
- Keep commands small, explicit, and scriptable.
- Require deliberate confirmation for every open or close command.
- Refuse offline, ambiguous, unsupported, or unsafe-to-operate devices.
- Wait for terminal state and distinguish acceptance from completed movement.
- Keep credentials, tokens, serials, account names, and device names outside the
  public repository.
- Preserve readable default output, redaction, and stable JSON output.
- Test all protocol and control logic with mocked HTTP; never operate live access
  equipment from an automated test.
- Update `README.md`, `SKILL.md`, and relevant files under `docs/` when command
  or authentication behavior changes.

## Layout

- `src/gatectl/auth.py` — OAuth/PKCE, login forms, and MFA
- `src/gatectl/http.py` — HTTP session behavior and error mapping
- `src/gatectl/client.py` — account/device reads and guarded operations
- `src/gatectl/storage.py` — private token and observation storage
- `src/gatectl/cli.py` — target selection, confirmation, and command dispatch
- `tests/` — offline unit tests with mocked MyQ responses
- `docs/` — authentication, operations, protocol, troubleshooting, and roadmap

## Development

Prefer `pipx` for daily installed use and `.venv` for development. Run the full
format, lint, secret-scan, and test sequence documented in `README.md` before
publishing. Live validation must be supervised and must not expose private
account, device, callback, or serial data.
