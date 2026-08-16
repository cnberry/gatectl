# Troubleshooting

## `No target config found`

Install and edit the example:

```bash
mkdir -p ~/.config/gatectl
install -m 600 config/targets.example.json ~/.config/gatectl/targets.json
gatectl inspect
```

Account and device names must match MyQ discovery exactly apart from case.

## `No MyQ session found`

Run `gatectl login`. If a recent password change revoked the refresh token,
complete a new MFA login rather than editing the token file.

## `browser verification challenge`

Stop retrying. Wait before running `gatectl doctor` once. A browser tab and the
CLI do not share cookies or PKCE state, so finishing a separate browser flow
cannot repair the current CLI process.

## `verification form was not recognized`

Run `gatectl doctor`. MyQ probably changed its form or returned an unexpected
page. Capture only a sanitized page summary; never attach cookies, passwords,
codes, or token responses to an issue.

## Command accepted but state timed out

Inspect the physical opening, then run:

```bash
gatectl status "Garage Door"
```

The device may still be in its close-warning delay, MyQ state may be stale, or
an obstruction may have caused a reversal. Do not repeatedly send commands to
force a transition.

## `401` or `403`

The client refreshes the OAuth token once and retries. If the second request
fails, run a fresh login. Persistent `403` responses can also indicate that
MyQ is blocking the unofficial client rather than rejecting the account.

## `429`

Wait before retrying. Repeated login, discovery, or polling requests can extend
rate limiting.
