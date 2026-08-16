# Authentication

`gatectl` reproduces the MyQ Android application's OAuth authorization-code
flow with PKCE. MyQ may require email or SMS verification and Firebase App
Check before it returns an authorization code.

## First login

1. Confirm that MyQ currently serves the expected sign-in form:

   ```bash
   gatectl doctor
   ```

2. Start one login and select the MFA delivery method:

   ```bash
   gatectl login --email you@example.com --mfa email
   # or: gatectl login --email you@example.com --mfa sms
   ```

3. Enter the password at the hidden prompt.
4. Enter the six-digit code sent by MyQ.
5. Confirm that `gatectl` reports a saved session.

The successful production flow used email MFA and the CLI prompts from start to
finish. Browser state is not transferred into the CLI process, so completing a
separate browser tab does not complete a waiting CLI login.

## Stored data

The password and verification code are not persisted. OAuth access and refresh
tokens are atomically written to `~/.config/gatectl/tokens.json` with mode
`0600`. Set `GATECTL_TOKEN_FILE` to override this path.

`gatectl` refreshes an expiring access token before an API request. If MyQ
returns `401` or `403`, the device client refreshes once and retries the same
idempotent operation.

## Browser challenges

When MyQ returns a Cloudflare or browser-verification page, `gatectl` exits with
`MyQ returned a browser verification challenge`. Do not loop login attempts;
repeated attempts can extend the challenge. Wait, run `gatectl doctor` once,
and begin a fresh login only after the normal form is reachable again.

## Credential hygiene

- Prefer the hidden password prompt over `MYQ_PASSWORD` so the password is not
  inherited by child processes or captured in shell tooling.
- Never put passwords, MFA codes, OAuth tokens, or raw HTTP captures in Git.
- Rotate any password that has been pasted into chat, logs, or a terminal
  transcript.
- Treat the token file like a password even when it lives in a private repo;
  the recommended policy is to keep it out of Git entirely.
