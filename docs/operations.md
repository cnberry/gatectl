# Operations and safety

## Target resolution

Every `status`, `open`, and `close` request uses the configured account name.
Device names are case-insensitive but otherwise exact. An operation proceeds
only when discovery returns exactly one matching device in that account.

The target file defaults to `~/.config/gatectl/targets.json`:

```json
{
  "account": "Demo Home",
  "devices": ["Driveway Gate", "Garage Door"]
}
```

## Command guardrails

Before sending a command, the client requires all of the following:

- device family is `garagedoor`;
- device is online;
- current state is the opposite terminal state (`closed` before open, `open`
  before close);
- MyQ reports `is_unattended_open_allowed` or
  `is_unattended_close_allowed` for the requested action;
- the URL is on the MyQ garage-device host and ends in exactly `/open` or
  `/close`.

Already-open/opening and already-closed/closing requests are idempotent no-ops.
Ambiguous states such as `stopped`, `transition`, or `autoreverse` are refused
instead of guessed.

## Confirmation and waiting

Interactive use requires typing `open` or `close`. `--yes` exists for a caller
that has already established an equivalent deliberate confirmation.

After MyQ accepts a command, `gatectl` polls current device state every two
seconds. A normal opening reports `opening` before `open`. A normal close can
remain `open` during the device's audible/visual warning delay, then reports
`closing` and `closed`.

`--wait 0` skips verification and reports only command acceptance. A timeout
means MyQ accepted the command but did not report the target state in time; it
does not prove the device failed to move. Inspect the area and run `status`.

## Physical safety

- Keep people, vehicles, animals, and objects clear of the opening.
- Do not bypass the opener's obstruction sensors or warning behavior.
- Do not build presence-based or geofence-based auto-open behavior without an
  independent safety and threat review.
- Keep an official app, wall control, or other supported recovery path.
- Never infer physical security solely from a cloud response.
