<p align="center">
  <img src="docs/assets/gatectl-hero.jpg" alt="Illustration of terminal-controlled driveway gate and garage door" width="100%">
</p>

# gatectl

`gatectl` is a small, dependency-free Python CLI for inspecting and operating
LiftMaster/MyQ residential gates and garage doors. It implements the current
OAuth/PKCE login flow, email or SMS MFA, refreshable sessions, account and
device discovery, state reads, and guarded open/close commands.

> [!WARNING]
> `gatectl` controls physical access equipment through an undocumented MyQ API.
> Keep the opening clear, retain a working official app or wall control, and do
> not use this project for unattended safety-critical automation.

## What it does

- discovers MyQ accounts, hubs, gates, and garage doors;
- reads exact-device state with serials redacted by default;
- stores OAuth tokens and observations outside the repository with mode `0600`;
- opens or closes one exact account/device match;
- refuses offline devices, ambiguous states, unsupported device families, and
  actions MyQ has not marked as safe for unattended operation;
- waits for MyQ to report the requested terminal state.

Python 3.11 or newer is required. There are no runtime package dependencies.

## Install

```bash
cd /path/to/private/home-config
./bin/bootstrap-ctls gatectl
```

The private `home-config` bootstrap is the canonical installer: it populates the
real inventory, calls this repository's stable `script/install` contract, and
creates `/usr/local/bin/gatectl` backed by an isolated system environment under
`/usr/local/lib/home-config/ctls`. For development without installation, prefix
commands with `PYTHONPATH=src python3 -m gatectl`.

## Configure private targets

Copy the public example to the private runtime location and replace the sample
names with exact values returned by `gatectl inspect`:

```bash
sudo install -d -m 700 /usr/local/config/gatectl
sudo install -m 600 config/targets.example.json /usr/local/config/gatectl/targets.json
```

```json
{
  "account": "Demo Home",
  "devices": ["Driveway Gate", "Garage Door"]
}
```

Use `GATECTL_CONFIG=/path/to/targets.json` or the global
`--config /path/to/targets.json` option to select another file. Real account,
device, host, and deployment data belongs in a private configuration repository,
not in a public fork of `gatectl`.

## Authenticate

Check the current sign-in form, then start one login:

```bash
gatectl doctor
gatectl login --email you@example.com --mfa email
```

The password prompt does not echo. Enter the six-digit email or SMS code when
asked. The password and MFA code are never stored; the resulting refreshable
session is written to `/usr/local/config/gatectl/tokens.json` with mode `0600`.

If MyQ returns a browser-verification challenge, stop and retry later instead
of repeatedly starting new logins. See [authentication](docs/authentication.md)
for the proven flow and recovery guidance.

## Inspect and read state

```bash
gatectl inspect
gatectl status
gatectl status "Garage Door"
```

`inspect` does not require a target config. `status` always scopes matches to
the configured account. Add `--json` for structured output or `--show-serials`
only when a serial is genuinely needed for diagnosis.

## Open and close

```bash
gatectl open "Garage Door"
gatectl close "Garage Door"
```

Interactive commands require typing the requested action. Deliberate
noninteractive callers may pass `--yes`. By default, `open` waits up to 45
seconds and `close` up to 60 seconds for the reported state. Override this with
`--wait SECONDS`; `--wait 0` returns after MyQ accepts the command without
claiming that movement completed.

```bash
gatectl close "Garage Door" --yes --wait 90
```

The successful live validation sequence was `closed → opening → open` followed
by `open → closing → closed`. Closing may remain `open` briefly while the
opener emits its warning signal. See [operations](docs/operations.md) for the
full safety model and state behavior.

## Runtime data

| Data | Default path | Git policy |
| --- | --- | --- |
| Target names | `/usr/local/config/gatectl/targets.json` | Private config repo only |
| OAuth tokens | `/usr/local/config/gatectl/tokens.json` | Private config/recovery seed only |
| Last observation | `~/.local/state/gatectl/last-observation.json` | Never commit |

Passwords and MFA codes are held only for the active login request. Serial
numbers are redacted in normal output and saved observations.

## Reliability and scope

MyQ does not publish or support this residential API. Endpoints, client
metadata, App Check behavior, MFA forms, rate limits, and Cloudflare challenges
can change without notice. `gatectl` intentionally has no toggle or arbitrary
write primitive; its only device writes are the guarded `open` and `close`
endpoints.

See [protocol notes](docs/protocol.md), [troubleshooting](docs/troubleshooting.md),
and the [roadmap](docs/roadmap.md) for more detail.

## Control-tool family

- [`gatectl`](https://github.com/cnberry/gatectl) — MyQ gate and garage-door
  status with guarded open/close.
- [`poolctl`](https://github.com/cnberry/poolctl) — Pentair ScreenLogic status,
  cleaner, and delay control.
- [`hottubctl`](https://github.com/cnberry/hottubctl) — Sundance SmartTub
  temperature and freshness inspection.
- [`switchctl`](https://github.com/cnberry/switchctl) — named local switch
  status and guarded power control.

Current and future `*ctl` tools favor small commands, private configuration,
readable output, safe JSON, guarded writes, post-write readback, a repo-owned
`script/install`, and explicit uncertainty.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/detect-secrets scan --baseline .secrets.baseline
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Tests use mocked HTTP responses and never contact or operate a real device.

## License and attribution

`gatectl` is released under the [MIT License](LICENSE). The OAuth form parsing,
current client metadata, and endpoint work build on Vadim Belov's MIT-licensed
[`bvdcode/myq-home-assistant`](https://github.com/bvdcode/myq-home-assistant).
See [NOTICE.md](NOTICE.md).
