---
name: gatectl
description: Inspect and operate configured MyQ gates and garage doors with the gatectl CLI. Use for login diagnostics, device inspection, status, and guarded open or close requests.
---

# gatectl

Use the installed `gatectl` CLI instead of ad-hoc MyQ requests when a command
already exists.

## Safety rules

- Treat passwords, MFA codes, tokens, callbacks, serials, account names, and
  device names as private data.
- Read state before a write when the exact target or current state is unclear.
- Preserve the CLI's exact account/device matching and safety refusals.
- Interactive writes require typing the action; deliberate automation may use
  `--yes` only after the target and physical area are clear.
- Report the terminal state returned after waiting. If `--wait 0` is used, say
  only that MyQ accepted the request.
- Never loop authentication attempts through a browser-verification challenge.

## Commands

```bash
gatectl doctor
gatectl login --email you@example.com --mfa email
gatectl inspect
gatectl status
gatectl status "Garage Door"
gatectl open "Garage Door"
gatectl close "Garage Door"
```

Use `--json` for structured reads and `--show-serials` only for a diagnosis that
genuinely requires them. If a command fails, quote the short error and do not
claim the device reached the requested state.
