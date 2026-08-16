# Protocol notes

`gatectl` uses an undocumented residential API that imitates the current MyQ
Android client. These notes describe the interoperability surface, not a stable
or supported public contract.

## Authentication

- OAuth 2.0 authorization code with PKCE
- scope: `MyQ_Residential offline_access`
- Android custom-scheme redirect
- form-driven email/password login
- email or SMS one-time verification
- Firebase App Check during authorization-code exchange
- refresh-token rotation when provided by MyQ

## Device API

| Purpose | Method and path |
| --- | --- |
| Accounts | `GET accounts.myq-cloud.com/api/v6.0/accounts` |
| Devices | `GET devices.myq-cloud.com/api/v6.2/Accounts/{account}/Devices` |
| Open | `PUT account-devices-gdo.myq-cloud.com/api/v6.0/accounts/{account}/door_openers/{serial}/open` |
| Close | `PUT account-devices-gdo.myq-cloud.com/api/v6.0/accounts/{account}/door_openers/{serial}/close` |

Commands normally return an empty success response. State confirmation comes
from subsequent device discovery, not from the command response itself.

The application identifiers in `src/gatectl/constants.py` are distributed
client metadata reproduced from a public reverse-engineering implementation;
they are not personal account credentials. They can rotate or stop working at
any time.

## Failure modes

- HTML form changes can break login parsing.
- Cloudflare can replace the login page with a browser challenge.
- Firebase App Check values can rotate.
- OAuth access or refresh tokens can be revoked early.
- The command host can return `401`, `403`, `429`, or disappear.
- Device state can lag command acceptance or report a safety reversal.

The implementation minimizes requests, refreshes once on authentication
failure, validates response shape, and never logs token values.
