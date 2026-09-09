# Luminal Open API Python SDK

Standalone Python 3 SDK for the enabled Luminal Open API controllers and webhook events.

## Properties

- Python 3.10+
- Runtime dependencies: standard library only

- Typed frozen dataclass models
- CamelCase JSON wire format with sorted keys, compact separators, UTF-8 encoding, and null omission
- `Long` serialization compatible with the JavaScript safe-integer API rule
- Bearer authorization for protected endpoints
- RSA `SHA256withRSA` signing and verification without third-party packages

## Installation

From this directory:

```bash
python3 -m pip install .
```

Or add the directory to `PYTHONPATH` during local development.

## Client usage

```python
from decimal import Decimal

from luminal_open_api_sdk import (
    CardIdRequest,
    CardLimitUpdateRequest,
    IssueCardRequest,
    LuminalOpenApiClient,
    MemberCardRechargeRequest,
)

client = LuminalOpenApiClient(
    "https://api.example.com",
    bearer_token="access-token",
)

cards = client.cards.list(request=...)
client.cards.freeze(CardIdRequest(member_card_id=123))
client.cards.modify_limit(CardLimitUpdateRequest(123, Decimal("500.00")))
client.cards.recharge(MemberCardRechargeRequest(123, Decimal("50.00"), "funding"))
```

The client accepts a gateway context path in `base_url`. Query strings and fragments are rejected.

Card-pool shared-account opening:

```python
from decimal import Decimal

from luminal_open_api_sdk import CardBinsRequest, CardPoolRequest, CreateSharedAccountRequest

pools = client.card_pools.list(CardPoolRequest())
pool = pools[0]
bins = client.cards.bins(
    CardBinsRequest(
        page_no=1,
        page_size=20,
        card_pool_id=pool.card_pool_id,
        card_type="SHARED",
    )
)
card_bin = bins.list[0]
created = client.shared_accounts.create(
    CreateSharedAccountRequest(
        card_bin_id=card_bin.card_bin_id,
        card_pool_id=pool.card_pool_id,
        recharge_amount=Decimal("100.00"),
        account_name="Main",
    )
)
```

`CardPoolRequest` only carries pool-level filters. Resolve a BIN after selecting the pool. Shared-account creation
may use `card_pool_id` when the BIN is selected from a pool; card issuance continues to require `card_bin_id`.

## Java `Long` serialization

Only fields typed as the SDK's `Long` marker use the JavaScript safe-integer compatibility rule for request
serialization:

- Values strictly greater than `-9_007_199_254_740_991` and strictly less than `9_007_199_254_740_991` remain JSON
  numbers.
- Values outside that open interval, including both boundary values, become decimal JSON strings.
- Response strings for typed `Long` fields decode back to Python `int` values.

Other Python `int` fields, including page indexes and page sizes, remain JSON numbers regardless of their value. Untyped
dictionary values follow normal Python JSON behavior and remain numbers.

Example:

```python
from dataclasses import dataclass
from luminal_open_api_sdk import serialize_json
from luminal_open_api_sdk.models import Long

@dataclass(frozen=True)
class Payload:
    amount: Long
    member_no: Long

assert serialize_json(Payload(100, 2_064_991_632_710_991_874)) == (
    b'{"amount":100,"memberNo":"2064991632710991874"}'
)
```

The rule applies to typed `Long` request fields during normal transmission. It also applies recursively to typed
`list[Long]` fields.

## Endpoint coverage

| API class           | Method          | HTTP path                                       |
|---------------------|-----------------|-------------------------------------------------|
| `AuthApi`           | `get_token`     | `POST /open-api/v1/auth/token`                  |
| `AuthApi`           | `refresh_token` | `POST /open-api/v1/auth/refresh-token`          |
| `AuthApi`           | `logout`        | `POST /open-api/v1/auth/logout`                 |
| `AccountsApi`       | `list`          | `POST /open-api/v1/accounts`                    |
| `TransactionsApi`   | `list`          | `POST /open-api/v1/transactions/list`           |
| `CardPoolsApi`      | `list`          | `POST /open-api/v1/cards/pools`                 |
| `SharedAccountsApi` | `create`        | `POST /open-api/v1/shared-account/create`       |
| `SharedAccountsApi` | `list`          | `POST /open-api/v1/shared-account/list`         |
| `SharedAccountsApi` | `increase`      | `POST /open-api/v1/shared-account/increase`     |
| `SharedAccountsApi` | `decrease`      | `POST /open-api/v1/shared-account/decrease`     |
| `SharedAccountsApi` | `cancel`        | `POST /open-api/v1/shared-account/cancel`       |
| `SharedAccountsApi` | `details`       | `POST /open-api/v1/shared-account/details`      |
| `SharedAccountsApi` | `transactions`  | `POST /open-api/v1/shared-account/transactions` |
| `CardsApi`          | `bins`          | `POST /open-api/v1/cards/bins`                  |
| `CardsApi`          | `issue`         | `POST /open-api/v1/cards/issue`                 |
| `CardsApi`          | `list`          | `POST /open-api/v1/cards/list`                  |
| `CardsApi`          | `cvv`           | `POST /open-api/v1/cards/cvv`                   |
| `CardsApi`          | `transactions`  | `POST /open-api/v1/cards/transactions`          |
| `CardsApi`          | `limit`         | `POST /open-api/v1/cards/limit`                 |
| `CardsApi`          | `modify_limit`  | `POST /open-api/v1/cards/limit/modify`          |
| `CardsApi`          | `modify_limit_async` | `POST /open-api/v1/cards/limit/modify/operation-record` |
| `CardsApi`          | `freeze`        | `POST /open-api/v1/cards/freeze`                |
| `CardsApi`          | `unfreeze`      | `POST /open-api/v1/cards/unfreeze`              |
| `CardsApi`          | `cancel`        | `POST /open-api/v1/cards/cancel`                |
| `CardsApi`          | `recharge`      | `POST /open-api/v1/cards/recharge`              |
| `CardsApi`          | `withdraw`      | `POST /open-api/v1/cards/withdraw`              |
| `CardsApi`          | `operation_records` | `POST /open-api/v1/cards/operation-record`      |
| `CardHoldersApi`    | `countries`     | `GET /open-api/v1/card-holders/countries`       |
| `CardHoldersApi`    | `add`           | `POST /open-api/v1/card-holders/add`            |
| `CardHoldersApi`    | `modify`        | `POST /open-api/v1/card-holders/modify`         |
| `CardHoldersApi`    | `detail`        | `POST /open-api/v1/card-holders/info/{card_holder_id}` |
| `CardHoldersApi`    | `page`          | `POST /open-api/v1/card-holders/page`           |
| `CardHoldersApi`    | `associated_cards` | `POST /open-api/v1/card-holders/card/page`      |
| `CardsApi`          | `issue_details` | `POST /open-api/v1/cards/issue/detail`          |
| `CardGroupsApi`     | `list`          | `POST /open-api/v1/cards/group`                 |
| `CardGroupsApi`     | `create`        | `POST /open-api/v1/cards/group/create`          |
| `CardGroupsApi`     | `update`        | `POST /open-api/v1/cards/group/update`          |
| `CardGroupsApi`     | `delete`        | `POST /open-api/v1/cards/group/delete`          |

All API responses must use the Luminal envelope:

```json
{"code":0,"msg":"success","data":{}}
```

Only HTTP `200` is treated as transport success and decoded as a Luminal `{code, msg, data}` envelope. Every other HTTP
status, malformed envelope, non-zero business code, or invalid JSON raises `LuminalApiException`. API response bodies
are capped at 1 MiB by default.

## Card issuance signing

`/cards/issue` uses two canonical serializations. The transmitted body follows the normal `Long` number/string rule. The
RSA `SHA256withRSA` signature input keeps every typed `Long`/ID value as a JSON number. Both omit null object fields and
sort object keys lexically. Use either a precomputed Base64 signature or an RSA private key object/PEM:

```python
from luminal_open_api_sdk import CardsApi, read_private_key

request = IssueCardRequest(...)
private_key = read_private_key(open("private_key.pem", encoding="utf-8").read())
task_id = client.cards.issue(request, private_key)
```

The `sign` header contains the Base64 signature. Do not log card numbers, CVV values, expiry values, private keys, or
bearer tokens.

Recharge, withdrawal, and asynchronous card-limit updates return operation-record identifiers. Recharge and withdrawal
use bearer authorization and JSON only; query their status with `cards.operation_record(...)` or
`cards.operation_records(...)`. `CardLimitUpdateRequest` accepts `daily_limit`, `month_limit`, and `total_limit`; its
legacy `card_type` field is retained for compatibility but is not sent.

## Webhooks

Verify the exact request body bytes before parsing. For duplicate-delivery protection, pass a shared process-local
`WebhookReplayGuard`:

```python
from luminal_open_api_sdk import WebhookReplayGuard, WebhookVerifier

replay_guard = WebhookReplayGuard(ttl_seconds=300, max_entries=10_000)

verified = WebhookVerifier.parse(
    event=request.headers["event"],
    event_id=request.headers["event_id"],
    raw_body=request.get_data(),
    signature=request.headers["sign"],
    public_key=public_key_pem,
    replay_guard=replay_guard
)
print(verified.type, verified.event_id, verified.payload)
```

Supported event headers:

- `CARD_TRANSACTIONS` → `TransactionWebhook`
- `CARD_SETTLE_STATUS` → `TransactionWebhook`
- `CARD_STATUS` → `CardStatusWebhook`
- `CARD_OPEN_STATUS` → `CardOpenStatusWebhook`
- `CARD_RECHARGE_STATUS` → `RechargeCardTransferStatusWebhook`
- `CARD_WITHDRAW_STATUS` → `RechargeCardTransferStatusWebhook`
- `CARD_LIMIT_STATUS` → `RechargeCardTransferStatusWebhook`
- `SHARED_ACCOUNT_OPEN_STATUS` → `SharedAccountOpenStatusWebhook`
- `SHARE_ACCOUNT_FUND_TRANSACTIONS` → `TransactionWebhook`

`WebhookEvent.raw_body` retains the exact bytes used for signature verification. Invalid headers, signatures, event
names, UTF-8, or payload JSON raise `WebhookVerificationException`. Webhook bodies are capped at 16 MiB by default. Set
`max_body_bytes` explicitly when the deployment contract requires a different bounded limit.

`WebhookReplayGuard` rejects a repeated `event_id` within its TTL. It is thread-safe but process-local. Production
deployments with multiple workers or instances must also enforce durable idempotency using a shared database, cache, or
queue keyed by `event_id`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Each controller endpoint has an independent `unittest.TestCase` class. Each webhook event has an independent test class.

### Sandbox integration tests

`tests/share_card_sandbox_open_api_integration_test.py` performs real HTTP requests against the fixed-BIN shared-card SDK flow:

- Auth: `get_token`, `refresh_token`, `logout`
- Accounts: `list`
- Transactions: `list`
- Shared accounts: `create`, `list`, `increase`, `decrease`, `details`, `transactions`
- Cards: `bins`, `issue`, `list`, `cvv`, `transactions`, `limit`, `modify_limit`, `freeze`, `unfreeze`, `cancel`,
  `issue_details`
- Card groups: `list`, `create`, `update`, `delete`

`tests/card_pool_shared_account_sandbox_open_api_integration_test.py` runs the same complete shared-card flow after
caching the plain card-pool list, selecting its first pool, resolving the fixed SHARED BIN `22346703`, and creating
the shared account with an initial amount of `100.00`.

Read-only endpoints run with only app credentials. The sandbox test class caches one authenticated client, reuses its
token, and refreshes it automatically when the token is near expiry or the API returns unauthorized. Side-effecting
endpoints now run by default; destructive endpoints also run by default. Sandbox credentials and the test private key
are defined directly in `tests/share_card_sandbox_open_api_integration_test.py` for demo use. Do not reuse them outside Sandbox or publish
this test source. SDK HTTP logging uses stdlib `logging` and is visible on the console with zero configuration. It is on
by default. Set `LUMINAL_OPEN_API_LOG_HTTP=0` to disable it for the sandbox integration test. Each enabled log is one
structured line with timestamp, level, logger, source
file/line, request method/URL/headers/body, or response URL/status/body. Header names and recursive JSON field names are
matched case-insensitively. `Authorization`, `Cookie`, `Set-Cookie`, `sign`, `accessToken`, `refreshToken`, `appSecret`,
`cvv`, `cardNo`, `cardNumber`, and `verifyCode` values become `<redacted>`. Non-JSON bodies become `<non-json N bytes>`.

For troubleshooting, both shared-card and recharge-card integration tests also enable original HTTP response logging by
default. Set `LUMINAL_OPEN_API_LOG_RAW_HTTP=0` to disable it. Original response logs can contain sensitive Sandbox data;
use them only for local debugging.

PowerShell:

```powershell
$env:LUMINAL_OPEN_API_LOG_HTTP = "1"
python -m unittest tests.share_card_sandbox_open_api_integration_test -v
python -m unittest tests.card_pool_shared_account_sandbox_open_api_integration_test -v
```

The recharge-card flow is covered separately by
`tests/recharge_card_sandbox_open_api_integration_test.py`:

```powershell
python -m unittest tests.recharge_card_sandbox_open_api_integration_test -v
```

The recharge-card test has Java-aligned Sandbox configuration in the test class, including app credentials and the test
private key. `LUMINAL_OPEN_API_RECHARGE_APP_ID`, `LUMINAL_OPEN_API_RECHARGE_APP_SECRET`, and
`LUMINAL_OPEN_API_RECHARGE_PRIVATE_KEY` / `LUMINAL_OPEN_API_RECHARGE_PRIVATE_KEY_PATH` can override the class defaults.
The recharge-specific variables fall back to their shared `LUMINAL_OPEN_API_*` counterparts where applicable;
`LUMINAL_OPEN_API_RECHARGE_CARD_BIN` defaults to `578391`.

SDK options:

- `app_id` / `app_secret`: auto token cache + automatic refresh
- `retry_unauthorized`: retry count after unauthorized response, default `1`
- `accept_language`: `en` default, `zh` optional
- `log_http`: request/response logging through the SDK's console handler, default `true`; set `False` to disable
- `log_raw_http`: original response logging for local diagnostics, default `false`

Sandbox test behavior:

- Executes every endpoint, including mutations and destructive operations; no opt-in environment switch is required.
- Uses only `cardBin=22346703`; queries its `cardBinId` at runtime.
- Creates each shared account, card group, and card-issue task at most once per test run, then reuses the cached result.
- Reuses one existing funded shared account for increase/decrease because newly submitted sandbox deposits can remain
  `PROCESSING`.
- `LUMINAL_OPEN_API_WALLET_CURRENCY` defaults to `USD`.

Override `LUMINAL_OPEN_API_BASE_URL` only when using another environment.
