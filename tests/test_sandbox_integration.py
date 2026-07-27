"""Real HTTP integration tests for every Luminal Open API SDK endpoint."""

from __future__ import annotations

import http.cookiejar
import json
import logging
import os
import ssl
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from luminal_open_api_sdk import (
    CardBinsRequest,
    CardGroupCreateRequest,
    CardGroupDeleteRequest,
    CardGroupRequest,
    CardGroupUpdateRequest,
    CardIdRequest,
    CardLimitUpdateRequest,
    CardOpenStatusWebhook,
    CardStatusWebhook,
    CardTransactionsRequest,
    CreateSharedAccountRequest,
    IssueCardDetailsRequest,
    IssueCardRequest,
    LuminalApiException,
    LuminalOpenApiClient,
    MemberCardPageRequest,
    SharedAccountBalanceRequest,
    SharedAccountGetRequest,
    SharedAccountOpenStatusWebhook,
    SharedAccountPageRequest,
    SharedAccountTransactionsRequest,
    TransactionWebhook,
    WalletInfoRequest,
    WalletTransactionRequest,
    WebhookEventType,
    WebhookVerificationException,
    read_private_key,
)
from luminal_open_api_sdk.codec import decode_value
from tests.support import SANDBOX_WEBHOOK_PUBLIC_KEY_PEM

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

DEFAULT_BASE_URL = "https://sandbox-openapi.luminalads.com"
SANDBOX_APP_ID = "lpsha6pj5mwsb7tz"
SANDBOX_APP_SECRET = "P11g59PXY33JjqL4CRJ2Oz3nfsjsWRKe"
SANDBOX_CARD_BIN = "22346703"
_LOGGER = logging.getLogger(__name__)
_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
_WEBHOOK_WAIT_SECONDS = float(os.getenv("LUMINAL_OPEN_API_WEBHOOK_WAIT_SECONDS", "120"))
_WEBHOOK_LOG_INTERVAL_SECONDS = 10.0
_WEBHOOK_CONDITION = threading.Condition()
_CARD_OPEN_WEBHOOKS: dict[str, CardOpenStatusWebhook] = {}
_CARD_STATUS_WEBHOOKS: dict[str, CardStatusWebhook] = {}
_SHARED_ACCOUNT_OPEN_WEBHOOKS: dict[str, SharedAccountOpenStatusWebhook] = {}
_SHARED_ACCOUNT_TRANSACTION_WEBHOOKS: dict[str, TransactionWebhook] = {}
_WEBHOOK_ERROR: Exception | None = None
_WEBHOOK_SERVER: ThreadingHTTPServer | None = None
_WEBHOOK_THREAD: threading.Thread | None = None
_CACHED_CLIENT: LuminalOpenApiClient | None = None
_CACHED_TOKEN: str | None = None
_CACHED_AUTH_TOKEN: Any = None
_CACHED_CARD_BIN: Any = None
_CACHED_SHARED_ACCOUNT: Any = None
_CACHED_BALANCE_SHARED_ACCOUNT: Any = None
_CACHED_SHARED_ACCOUNT_INCREASE: Any = None
_SHARED_ACCOUNT_CREATE_ATTEMPTED = False
_SHARED_ACCOUNT_CREATE_ERROR: LuminalApiException | None = None
_CACHED_CARD_GROUP: Any = None
_CARD_GROUP_CREATE_ATTEMPTED = False
_CARD_GROUP_CREATE_ERROR: LuminalApiException | None = None
_CACHED_DELETE_CARD_GROUP: Any = None
_DELETE_CARD_GROUP_CREATE_ATTEMPTED = False
_DELETE_CARD_GROUP_CREATE_ERROR: LuminalApiException | None = None
_CACHED_ISSUE_TASK_ID: int | None = None
_CACHED_ISSUE_ERROR: Exception | None = None
_ISSUE_ATTEMPTED = False
_SANDBOX_URLOPEN = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
).open
_TEST_LABELS = {
    "SandboxAuthApiTest.test_get_token_from_sandbox": "auth: get token",
    "SandboxAuthApiTest.test_refresh_token_from_sandbox": "auth: refresh token",
    "SandboxAuthApiTest.test_logout_from_sandbox": "auth: logout",
    "SandboxAuthApiTest.test_get_token_after_logout_from_sandbox": "auth: get token after logout",
    "SandboxSharedAccountsApiTest.test_create_shared_account_from_sandbox": "shared accounts: create account",
    "SandboxCardGroupsApiTest.test_create_card_group_from_sandbox": "card groups: create card group",
    "SandboxSharedAccountsApiTest.test_increase_shared_account_from_sandbox": "shared accounts: increase balance",
    "SandboxCardsApiTest.test_issue_card_from_sandbox": "cards: issue card",
    "SandboxCardsApiTest.test_wait_for_card_open_status_webhook_from_sandbox": "cards: wait for open webhook",
    "SandboxSharedAccountsApiTest.test_decrease_shared_account_from_sandbox": "shared accounts: decrease balance",
    "SandboxAccountsApiTest.test_list_accounts_from_sandbox": "accounts: list wallet accounts",
    "SandboxTransactionsApiTest.test_list_transactions_from_sandbox": "transactions: list wallet transactions",
    "SandboxSharedAccountsApiTest.test_list_shared_accounts_from_sandbox": "shared accounts: list accounts",
    "SandboxSharedAccountsApiTest.test_get_shared_account_details_from_sandbox": "shared accounts: get account details",
    "SandboxSharedAccountsApiTest.test_list_shared_account_transactions_from_sandbox": "shared accounts: list account transactions",
    "SandboxCardsApiTest.test_list_cards_from_sandbox": "cards: list member cards",
    "SandboxCardsApiTest.test_get_card_cvv_from_sandbox": "cards: retrieve CVV",
    "SandboxCardsApiTest.test_list_card_transactions_from_sandbox": "cards: list card transactions",
    "SandboxCardsApiTest.test_get_card_limit_from_sandbox": "cards: get card limit",
    "SandboxCardsApiTest.test_modify_card_limit_from_sandbox": "cards: update card limit",
    "SandboxCardsApiTest.test_get_card_issue_details_from_sandbox": "cards: get issue details",
    "SandboxCardGroupsApiTest.test_list_card_groups_from_sandbox": "card groups: list card groups",
    "SandboxCardGroupsApiTest.test_update_card_group_from_sandbox": "card groups: update card group",
    "SandboxCardsApiTest.test_freeze_card_from_sandbox": "cards: freeze",
    "SandboxCardsApiTest.test_unfreeze_card_from_sandbox": "cards: unfreeze",
    "SandboxCardsApiTest.test_cancel_card_from_sandbox": "cards: cancel card",
    "SandboxCardGroupsApiTest.test_delete_card_group_from_sandbox": "card groups: delete card group",
}


def _webhook_payload_type(event_type: WebhookEventType) -> type[Any]:
    if event_type is WebhookEventType.CARD_OPEN_STATUS:
        return CardOpenStatusWebhook
    if event_type is WebhookEventType.CARD_STATUS:
        return CardStatusWebhook
    if event_type is WebhookEventType.SHARED_ACCOUNT_OPEN_STATUS:
        return SharedAccountOpenStatusWebhook
    return TransactionWebhook


def _record_webhook(event_type: WebhookEventType, payload: Any) -> None:
    with _WEBHOOK_CONDITION:
        if event_type is WebhookEventType.CARD_OPEN_STATUS:
            results = payload.list
            if results is not None and all(
                    result.card_status in {"SUCCESS", "FAIL"} for result in results
            ):
                _CARD_OPEN_WEBHOOKS[str(payload.card_apply_task_id)] = payload
        elif event_type is WebhookEventType.CARD_STATUS:
            _CARD_STATUS_WEBHOOKS[str(payload.member_card_id)] = payload
        elif event_type is WebhookEventType.SHARED_ACCOUNT_OPEN_STATUS:
            if payload.status in {"SUCCESS", "FAIL"}:
                _SHARED_ACCOUNT_OPEN_WEBHOOKS[str(payload.member_shared_account_id)] = payload
        elif payload.status in {"SUCCESS", "FAIL"}:
            _SHARED_ACCOUNT_TRANSACTION_WEBHOOKS[str(payload.shared_account_transaction_id)] = payload
        _WEBHOOK_CONDITION.notify_all()


def _record_webhook_error(exc: Exception) -> None:
    global _WEBHOOK_ERROR
    with _WEBHOOK_CONDITION:
        _WEBHOOK_ERROR = exc
        _WEBHOOK_CONDITION.notify_all()


class _WebhookRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != os.getenv("LUMINAL_OPEN_API_WEBHOOK_PATH", "/luminal-open-api-webhook"):
            self._respond(404)
            return
        event = self.headers.get("event", "")
        event_id = self.headers.get("event_id", "")
        signature = self.headers.get("sign", "")
        if not event.strip() or not event_id.strip() or not signature.strip():
            self._respond(400)
            return
        try:
            event_type = WebhookEventType(event)
        except ValueError:
            self._respond(200)
            return
        if event_type not in {
            WebhookEventType.CARD_OPEN_STATUS,
            WebhookEventType.CARD_STATUS,
            WebhookEventType.SHARED_ACCOUNT_OPEN_STATUS,
            WebhookEventType.SHARE_ACCOUNT_FUND_TRANSACTIONS,
        }:
            self._respond(200)
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
            if content_length < 0:
                raise ValueError
        except ValueError:
            self._respond(400)
            return
        if content_length > _WEBHOOK_MAX_BODY_BYTES:
            self._respond(413)
            return
        body = self.rfile.read(content_length)
        try:
            client = _CACHED_CLIENT or LuminalOpenApiClient(
                os.getenv("LUMINAL_OPEN_API_BASE_URL", DEFAULT_BASE_URL),
                log_http=os.getenv("LUMINAL_OPEN_API_LOG_HTTP", "1") == "1",
            )
            payload = client.parse_webhook(
                event_type,
                event_id,
                body,
                signature,
                SANDBOX_WEBHOOK_PUBLIC_KEY_PEM,
            ).payload
            _record_webhook(event_type, payload)
        except WebhookVerificationException as exc:
            _record_webhook_error(exc)
            self._respond(401)
            return
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            _record_webhook_error(exc)
            self._respond(400)
            return
        self._respond(200)

    def do_GET(self) -> None:
        self._respond(405)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _respond(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


def setUpModule() -> None:
    global _WEBHOOK_SERVER, _WEBHOOK_THREAD
    host = os.getenv("LUMINAL_OPEN_API_WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("LUMINAL_OPEN_API_WEBHOOK_PORT", "18081"))
    _WEBHOOK_SERVER = ThreadingHTTPServer((host, port), _WebhookRequestHandler)
    _WEBHOOK_SERVER.daemon_threads = True
    _WEBHOOK_THREAD = threading.Thread(target=_WEBHOOK_SERVER.serve_forever, name="sandbox-webhook", daemon=True)
    _WEBHOOK_THREAD.start()
    _LOGGER.info("waiting for sandbox webhooks on %s:%s%s", host, port, os.getenv(
        "LUMINAL_OPEN_API_WEBHOOK_PATH", "/luminal-open-api-webhook"
    ))


def tearDownModule() -> None:
    if _WEBHOOK_SERVER is not None:
        _WEBHOOK_SERVER.shutdown()
        _WEBHOOK_SERVER.server_close()
    if _WEBHOOK_THREAD is not None:
        _WEBHOOK_THREAD.join(timeout=5)


def _await_webhook(store: dict[str, Any], key: Any, operation: str) -> Any:
    started_at = time.monotonic()
    deadline = time.monotonic() + _WEBHOOK_WAIT_SECONDS
    next_log = time.monotonic() + _WEBHOOK_LOG_INTERVAL_SECONDS
    with _WEBHOOK_CONDITION:
        while True:
            if _WEBHOOK_ERROR is not None:
                raise AssertionError(f"{operation} webhook listener failed") from _WEBHOOK_ERROR
            payload = store.pop(str(key), None)
            if payload is not None:
                return payload
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for {operation} webhook")
            _WEBHOOK_CONDITION.wait(min(remaining, max(0.0, next_log - time.monotonic())))
            if time.monotonic() >= next_log:
                event, correlation_id = _webhook_wait_details(operation, key)
                _LOGGER.info(
                    "Waiting for %s transactionId=%s webhook, elapsed=%ds",
                    event,
                    correlation_id,
                    int(time.monotonic() - started_at),
                )
                next_log = time.monotonic() + _WEBHOOK_LOG_INTERVAL_SECONDS

def _webhook_wait_details(operation: str, key: Any) -> tuple[str, str]:
    event = {
        "shared-account creation": "SHARED_ACCOUNT_OPEN_STATUS",
        "shared-account transaction": "FUND_TRANSACTION",
        "card status": "CARD_STATUS",
        "card issuance": "CARD_OPEN_STATUS",
    }.get(operation, operation)
    return event, str(key)


def _sandbox_urlopen(
        request: Any,
        *,
        timeout: float,
        _urlopen: Any = _SANDBOX_URLOPEN,
        _sleep: Any = time.sleep,
) -> Any:
    """Retry only TLS handshake EOFs; the HTTP request was not sent yet."""

    for attempt in range(3):
        try:
            return _urlopen(request, timeout=timeout)
        except urllib.error.URLError as exc:
            if attempt == 2 or not isinstance(exc.reason, ssl.SSLEOFError):
                raise
            _sleep(0.2)
    raise AssertionError("unreachable")


class _SandboxIntegrationTestCase(unittest.TestCase):
    """Shared real-HTTP setup; no mocks."""

    def run(self, result: unittest.TestResult | None = None) -> unittest.TestResult:
        if result is None:
            result = self.defaultTestResult()
        label = _TEST_LABELS.get(
            f"{type(self).__name__}.{self._testMethodName}",
            self._testMethodName,
        )
        failures_before = len(result.failures) + len(result.errors)
        _LOGGER.info("START %s", label)
        try:
            return super().run(result)
        finally:
            failures_after = len(result.failures) + len(result.errors)
            status = "FAILED" if failures_after > failures_before else "PASSED"
            _LOGGER.info("END %s status=%s", label, status)

    def _credentials(self) -> tuple[str, str]:
        return SANDBOX_APP_ID, SANDBOX_APP_SECRET

    def _client(self) -> LuminalOpenApiClient:
        global _CACHED_CLIENT
        if _CACHED_CLIENT is None:
            app_id, app_secret = self._credentials()
            _CACHED_CLIENT = LuminalOpenApiClient(
                os.getenv("LUMINAL_OPEN_API_BASE_URL", DEFAULT_BASE_URL),
                timeout=float(os.getenv("LUMINAL_OPEN_API_TIMEOUT", "15")),
                app_id=app_id,
                app_secret=app_secret,
                retry_unauthorized=int(os.getenv("LUMINAL_OPEN_API_RETRY_UNAUTHORIZED", "1")),
                accept_language=os.getenv("LUMINAL_OPEN_API_ACCEPT_LANGUAGE", "en"),
                log_http=os.getenv("LUMINAL_OPEN_API_LOG_HTTP", "1") == "1",
                opener=_sandbox_urlopen,
            )
        self._active_client = _CACHED_CLIENT
        return _CACHED_CLIENT

    def _authenticated_client(self) -> LuminalOpenApiClient:
        global _CACHED_TOKEN
        if _CACHED_TOKEN is None:
            self._prime_auth_cycle()
        return self._client()

    def _auth_client(self) -> LuminalOpenApiClient:
        app_id, app_secret = self._credentials()
        return LuminalOpenApiClient(
            os.getenv("LUMINAL_OPEN_API_BASE_URL", DEFAULT_BASE_URL),
            timeout=float(os.getenv("LUMINAL_OPEN_API_TIMEOUT", "15")),
            app_id=app_id,
            app_secret=app_secret,
            retry_unauthorized=int(os.getenv("LUMINAL_OPEN_API_RETRY_UNAUTHORIZED", "1")),
            accept_language=os.getenv("LUMINAL_OPEN_API_ACCEPT_LANGUAGE", "en"),
            log_http=os.getenv("LUMINAL_OPEN_API_LOG_HTTP", "1") == "1",
            opener=_sandbox_urlopen,
        )

    def _get_token_from_sandbox(self) -> Any:
        global _CACHED_AUTH_TOKEN, _CACHED_TOKEN
        app_id, app_secret = self._credentials()
        client = self._auth_client()
        token = None
        last_exc = None
        for _ in range(3):
            try:
                token = client.auth.get_token(app_id, app_secret)
                break
            except LuminalApiException as exc:
                last_exc = exc
                if "system error" not in str(exc).lower() and "not logged in" not in str(exc).lower():
                    raise
        if token is None:
            raise last_exc
        self.assertIsNotNone(token)
        self.assertTrue(token.access_token)
        self.assertTrue(token.refresh_token)
        _CACHED_AUTH_TOKEN = token
        _CACHED_TOKEN = token.access_token
        cached_client = self._client()
        cached_client._token_cache._token = token
        cached_client._token_cache._acquired_at_ms = int(time.time() * 1000)
        return token

    def _refresh_token_from_sandbox(self) -> Any:
        global _CACHED_AUTH_TOKEN, _CACHED_TOKEN
        token = _CACHED_AUTH_TOKEN or self._get_token_from_sandbox()
        authed = self._client().with_bearer_token(token.access_token)
        refreshed = None
        last_exc = None
        for _ in range(3):
            try:
                refreshed = authed.auth.refresh_token(token.refresh_token)
                break
            except LuminalApiException as exc:
                last_exc = exc
                if "not logged in" not in str(exc).lower() and "system error" not in str(exc).lower():
                    raise
        if refreshed is not None:
            self.assertTrue(refreshed.access_token)
            self.assertTrue(refreshed.token_type)
            _CACHED_AUTH_TOKEN = refreshed
            _CACHED_TOKEN = refreshed.access_token
            self._client()._token_cache._token = refreshed
            self._client()._token_cache._acquired_at_ms = int(time.time() * 1000)
        return refreshed

    def _logout_from_sandbox(self) -> bool:
        token = _CACHED_AUTH_TOKEN or self._get_token_from_sandbox()
        client = self._client().with_bearer_token(token.access_token)
        try:
            result = client.auth.logout()
            self.assertIsInstance(result, bool)
            return result
        except LuminalApiException as exc:
            self.assertIn("not logged in", str(exc).lower())
            return False

    def _prime_auth_cycle(self) -> None:
        self._get_token_from_sandbox()
        self._refresh_token_from_sandbox()
        self._logout_from_sandbox()
        self._get_token_from_sandbox()

    def _run_mutations(self) -> None:
        return

    def _run_destructive_mutations(self) -> None:
        return

    def _assert_page(self, page: Any) -> None:
        self.assertIsNotNone(page)
        self.assertIsInstance(page.list, list)

    def _first_page_item(self, page: Any, label: str) -> Any:
        self._assert_page(page)
        self.assertTrue(page.list, f"{label} returned no rows")
        return page.list[0]

    def _first_card(self) -> Any:
        page = self._authenticated_client().cards.list(
            MemberCardPageRequest(
                page_no=1,
                page_size=1,
                card_type=self._card_type(),
                card_bin=SANDBOX_CARD_BIN,
            )
        )
        return self._first_page_item(page, "cards.list")

    def _await_shared_account_open(self, account_id: Any) -> None:
        try:
            webhook = _await_webhook(
                _SHARED_ACCOUNT_OPEN_WEBHOOKS, account_id, "shared-account creation"
            )
        except TimeoutError:
            details = self._authenticated_client().shared_accounts.details(
                SharedAccountGetRequest(member_shared_account_id=account_id)
            )
            self.assertIsNotNone(details)
            self.assertTrue(details.member_shared_account_id)
            return
        self.assertEqual(str(account_id), str(webhook.member_shared_account_id))
        self.assertEqual("SUCCESS", webhook.status, "shared-account creation webhook reported failure")

    def _await_shared_account_transaction(self, transaction_id: Any, account_id: Any) -> None:
        try:
            webhook = _await_webhook(
                _SHARED_ACCOUNT_TRANSACTION_WEBHOOKS, transaction_id, "shared-account transaction"
            )
            self.assertEqual(str(transaction_id), str(webhook.shared_account_transaction_id))
            status = webhook.status
        except TimeoutError:
            page = self._authenticated_client().shared_accounts.transactions(
                SharedAccountTransactionsRequest(
                    page_no=1,
                    page_size=1,
                    shared_account_transaction_id=int(transaction_id),
                    member_shared_account_id=account_id,
                )
            )
            self._assert_page(page)
            transaction = next(
                (
                    item
                    for item in page.list
                    if str(getattr(item, "shared_account_transaction_id", "")) == str(transaction_id)
                ),
                None,
            )
            self.assertIsNotNone(transaction, "shared-account transaction fallback returned no matching row")
            status = transaction.status
        self.assertEqual("SUCCESS", status, f"shared-account transaction finished with status {status}")

    def _await_card_status(self, card_id: Any, expected: str) -> None:
        try:
            webhook = _await_webhook(_CARD_STATUS_WEBHOOKS, card_id, "card status")
        except TimeoutError:
            page = self._authenticated_client().cards.list(
                MemberCardPageRequest(
                    page_no=1,
                    page_size=1,
                    member_card_id=card_id,
                    card_type=self._card_type(),
                )
            )
            card = self._first_page_item(page, "cards.list")
            self.assertEqual(expected, card.status.upper())
            return
        self.assertEqual(str(card_id), str(webhook.member_card_id))
        self.assertEqual(expected, webhook.card_status.upper())

    def _await_card_issue(self, task_id: Any) -> None:
        try:
            webhook = _await_webhook(_CARD_OPEN_WEBHOOKS, task_id, "card issuance")
        except TimeoutError:
            details = self._authenticated_client().cards.issue_details(
                IssueCardDetailsRequest(task_id=task_id)
            )
            self.assertIsInstance(details, list)
            result = next(
                (
                    item
                    for item in details
                    if item.member_card_id and item.card_status not in {None, "APPLYING"}
                ),
                None,
            )
            self.assertIsNotNone(result, "card issuance fallback returned no completed card")
            self.assertNotEqual("FAIL", result.card_status, result.message)
            self._await_card_status(result.member_card_id, "ACTIVE")
            return
        self.assertEqual(str(task_id), str(webhook.card_apply_task_id))
        self.assertTrue(webhook.list, "card issuance webhook returned no results")
        result = next((item for item in webhook.list if item.member_card_id), None)
        self.assertIsNotNone(result, "card issuance webhook returned no card ID")
        self.assertEqual("SUCCESS", result.card_status, result.message)
        details = self._authenticated_client().cards.issue_details(IssueCardDetailsRequest(task_id=task_id))
        self.assertIsInstance(details, list)
        confirmed = next(
            (item for item in details if str(item.member_card_id) == str(result.member_card_id)), None
        )
        self.assertIsNotNone(confirmed, "issued card was absent from issue-details response")
        self.assertNotIn(confirmed.card_status, {None, "APPLYING"})
        self._await_card_status(result.member_card_id, "ACTIVE")

    def _first_shared_account(self) -> Any:
        global _CACHED_SHARED_ACCOUNT, _SHARED_ACCOUNT_CREATE_ATTEMPTED, _SHARED_ACCOUNT_CREATE_ERROR
        if _CACHED_SHARED_ACCOUNT is not None:
            return _CACHED_SHARED_ACCOUNT
        if not _SHARED_ACCOUNT_CREATE_ATTEMPTED:
            _SHARED_ACCOUNT_CREATE_ATTEMPTED = True
            try:
                created = self._authenticated_client().shared_accounts.create(
                    CreateSharedAccountRequest(
                        card_bin_id=self._first_card_bin().card_bin_id,
                        recharge_amount=Decimal("1"),
                        account_name=f"sdk-sandbox-{uuid.uuid4().hex[:12]}",
                    )
                )
                self.assertIsNotNone(created)
                self.assertTrue(created.member_shared_account_id)
                self._await_shared_account_open(created.member_shared_account_id)
                _CACHED_SHARED_ACCOUNT = created
            except LuminalApiException as exc:
                _SHARED_ACCOUNT_CREATE_ERROR = exc
        if _CACHED_SHARED_ACCOUNT is None:
            page = self._authenticated_client().shared_accounts.list(
                SharedAccountPageRequest(page_no=1, page_size=10)
            )
            self._assert_page(page)
            _CACHED_SHARED_ACCOUNT = next(
                (
                    item
                    for item in page.list
                    if getattr(item, "status", None) == "ACTIVE"
                       and str(getattr(item, "card_bin", "")) == SANDBOX_CARD_BIN
                       and getattr(item, "card_bin_id", None) == self._first_card_bin().card_bin_id
                ),
                None,
            )
        if _CACHED_SHARED_ACCOUNT is None and _SHARED_ACCOUNT_CREATE_ERROR is not None:
            raise _SHARED_ACCOUNT_CREATE_ERROR
        self.assertIsNotNone(_CACHED_SHARED_ACCOUNT)
        self.assertTrue(_CACHED_SHARED_ACCOUNT.member_shared_account_id)
        return _CACHED_SHARED_ACCOUNT

    def _first_card_group(self) -> Any:
        page = self._authenticated_client().card_groups.list(
            CardGroupRequest(page_no=1, page_size=10, card_type=self._card_type())
        )
        self._assert_page(page)
        for item in page.list:
            if getattr(item, "card_group_name", None) == "default":
                return item
        return self._first_page_item(page, "card_groups.list")

    def _created_card_group(self) -> Any:
        global _CACHED_CARD_GROUP, _CARD_GROUP_CREATE_ATTEMPTED, _CARD_GROUP_CREATE_ERROR
        if not _CARD_GROUP_CREATE_ATTEMPTED:
            _CARD_GROUP_CREATE_ATTEMPTED = True
            try:
                _CACHED_CARD_GROUP = self._authenticated_client().card_groups.create(
                    CardGroupCreateRequest(
                        card_group_name=f"sdk-sandbox-{uuid.uuid4().hex[:12]}",
                        card_type=self._card_type(),
                    )
                )
            except LuminalApiException as exc:
                _CARD_GROUP_CREATE_ERROR = exc
        if _CARD_GROUP_CREATE_ERROR is not None:
            raise _CARD_GROUP_CREATE_ERROR
        self.assertIsNotNone(_CACHED_CARD_GROUP)
        self.assertTrue(_CACHED_CARD_GROUP.card_group_id)
        return _CACHED_CARD_GROUP

    def _delete_card_group(self) -> Any:
        global _CACHED_DELETE_CARD_GROUP, _DELETE_CARD_GROUP_CREATE_ATTEMPTED, _DELETE_CARD_GROUP_CREATE_ERROR
        if not _DELETE_CARD_GROUP_CREATE_ATTEMPTED:
            _DELETE_CARD_GROUP_CREATE_ATTEMPTED = True
            try:
                _CACHED_DELETE_CARD_GROUP = self._authenticated_client().card_groups.create(
                    CardGroupCreateRequest(
                        card_group_name=f"sdk-sandbox-delete-group-{uuid.uuid4().hex[:12]}",
                        card_type=self._card_type(),
                    )
                )
            except LuminalApiException as exc:
                _DELETE_CARD_GROUP_CREATE_ERROR = exc
        if _DELETE_CARD_GROUP_CREATE_ERROR is not None:
            raise _DELETE_CARD_GROUP_CREATE_ERROR
        self.assertIsNotNone(_CACHED_DELETE_CARD_GROUP)
        self.assertTrue(_CACHED_DELETE_CARD_GROUP.card_group_id)
        return _CACHED_DELETE_CARD_GROUP

    def _balance_shared_account(self) -> Any:
        global _CACHED_BALANCE_SHARED_ACCOUNT
        if _CACHED_BALANCE_SHARED_ACCOUNT is not None:
            return _CACHED_BALANCE_SHARED_ACCOUNT
        card_bin_id = self._first_card_bin().card_bin_id
        page_no = 1
        while True:
            page = self._authenticated_client().shared_accounts.list(
                SharedAccountPageRequest(page_no=page_no, page_size=100)
            )
            matches = [
                item
                for item in page.list
                if getattr(item, "status", None) == "ACTIVE"
                   and str(getattr(item, "card_bin", "")) == SANDBOX_CARD_BIN
                   and getattr(item, "card_bin_id", None) == card_bin_id
                   and (getattr(item, "balance", None) or Decimal("0")) >= Decimal("1")
            ]
            if matches:
                _CACHED_BALANCE_SHARED_ACCOUNT = max(
                    matches, key=lambda item: getattr(item, "balance", None) or Decimal("0")
                )
                return _CACHED_BALANCE_SHARED_ACCOUNT
            if page_no * 100 >= page.total:
                self.fail(f"no funded ACTIVE shared account found for cardBin {SANDBOX_CARD_BIN}")
            page_no += 1

    def _increase_shared_account_once(self) -> Any:
        global _CACHED_SHARED_ACCOUNT_INCREASE
        if _CACHED_SHARED_ACCOUNT_INCREASE is None:
            account_id = self._balance_shared_account().member_shared_account_id
            increased = self._authenticated_client().shared_accounts.increase(
                SharedAccountBalanceRequest(
                    member_shared_account_id=account_id,
                    amount=Decimal("1"),
                )
            )
            self.assertIsNotNone(increased)
            self.assertTrue(increased.shared_account_transaction_id)
            self._await_shared_account_transaction(increased.shared_account_transaction_id, account_id)
            _CACHED_SHARED_ACCOUNT_INCREASE = increased
        return _CACHED_SHARED_ACCOUNT_INCREASE

    def _first_card_bin(self) -> Any:
        global _CACHED_CARD_BIN
        if _CACHED_CARD_BIN is None:
            page = self._authenticated_client().cards.bins(
                CardBinsRequest(
                    page_no=1,
                    page_size=10,
                    card_type=self._card_type(),
                    card_bin=SANDBOX_CARD_BIN,
                )
            )
            self._assert_page(page)
            _CACHED_CARD_BIN = next(
                (item for item in page.list if str(item.card_bin) == SANDBOX_CARD_BIN),
                None,
            )
            self.assertIsNotNone(_CACHED_CARD_BIN, f"cardBin {SANDBOX_CARD_BIN} not found")
            self.assertIsNotNone(_CACHED_CARD_BIN.card_bin_id)
        return _CACHED_CARD_BIN

    def _first_active_card(self) -> Any:
        page = self._authenticated_client().cards.list(
            MemberCardPageRequest(
                page_no=1,
                page_size=10,
                status="ACTIVE",
                card_bin=SANDBOX_CARD_BIN,
                card_type=self._card_type(),
            )
        )
        self._assert_page(page)
        for item in page.list:
            if getattr(item, "status", None) == "ACTIVE":
                return item
        return self._first_page_item(page, "cards.list")


class SandboxAuthApiTest(_SandboxIntegrationTestCase):
    def test_get_token_from_sandbox(self) -> None:
        self._get_token_from_sandbox()

    def test_refresh_token_from_sandbox(self) -> None:
        refreshed = self._refresh_token_from_sandbox()
        self.assertIsNotNone(refreshed)

    def test_logout_from_sandbox(self) -> None:
        self.assertIsInstance(self._logout_from_sandbox(), bool)

    def test_get_token_after_logout_from_sandbox(self) -> None:
        self._get_token_from_sandbox()


class SandboxAccountsApiTest(_SandboxIntegrationTestCase):
    def test_list_accounts_from_sandbox(self) -> None:
        result = self._authenticated_client().accounts.list(
            WalletInfoRequest(
                page_no=1,
                page_size=10,
                currency=os.getenv("LUMINAL_OPEN_API_WALLET_CURRENCY", "USD"),
            )
        )
        self._assert_page(result)


class SandboxTransactionsApiTest(_SandboxIntegrationTestCase):
    def test_list_transactions_from_sandbox(self) -> None:
        result = self._authenticated_client().transactions.list(
            WalletTransactionRequest(page_no=1, page_size=10)
        )
        self._assert_page(result)


class SandboxSharedAccountsApiTest(_SandboxIntegrationTestCase):
    def _card_type(self) -> str:
        return os.getenv("LUMINAL_OPEN_API_CARD_TYPE", "SHARED")

    def test_create_shared_account_from_sandbox(self) -> None:
        self._run_mutations()
        result = self._first_shared_account()
        self.assertTrue(result.member_shared_account_id)

    def test_list_shared_accounts_from_sandbox(self) -> None:
        result = self._authenticated_client().shared_accounts.list(
            SharedAccountPageRequest(page_no=1, page_size=10)
        )
        self._assert_page(result)

    def test_increase_shared_account_from_sandbox(self) -> None:
        self._run_mutations()
        result = self._increase_shared_account_once()
        self.assertIsNotNone(result)
        self.assertTrue(result.shared_account_transaction_id)

    def test_decrease_shared_account_from_sandbox(self) -> None:
        self._run_mutations()
        self._increase_shared_account_once()
        account_id = self._balance_shared_account().member_shared_account_id
        result = self._authenticated_client().shared_accounts.decrease(
            SharedAccountBalanceRequest(
                member_shared_account_id=account_id,
                amount=Decimal("1"),
            )
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.shared_account_transaction_id)
        self._await_shared_account_transaction(result.shared_account_transaction_id, account_id)

    def test_get_shared_account_details_from_sandbox(self) -> None:
        result = self._authenticated_client().shared_accounts.details(
            SharedAccountGetRequest(member_shared_account_id=self._first_shared_account().member_shared_account_id)
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.member_shared_account_id)

    def test_list_shared_account_transactions_from_sandbox(self) -> None:
        result = self._authenticated_client().shared_accounts.transactions(
            SharedAccountTransactionsRequest(page_no=1, page_size=10)
        )
        self._assert_page(result)


class SandboxCardsApiTest(_SandboxIntegrationTestCase):
    def _card_type(self) -> str:
        return os.getenv("LUMINAL_OPEN_API_CARD_TYPE", "SHARED")

    def _issue_request(self) -> IssueCardRequest:
        card_bin = self._first_card_bin()
        shared_account = self._first_shared_account()
        card_group = self._first_card_group()
        return IssueCardRequest(
            apply_count=1,
            card_bin_id=card_bin.card_bin_id,
            card_group_id=card_group.card_group_id,
            card_name=os.getenv("LUMINAL_OPEN_API_ISSUE_CARD_NAME", f"sdk-sandbox-{uuid.uuid4().hex[:12]}"),
            card_type=self._card_type(),
            member_shared_account_id=shared_account.member_shared_account_id,
            month_limit=Decimal("1"),
            recharge_amount=Decimal("1"),
        )

    def _issue_once(self):
        global _CACHED_ISSUE_TASK_ID, _CACHED_ISSUE_ERROR, _ISSUE_ATTEMPTED
        if not _ISSUE_ATTEMPTED:
            _ISSUE_ATTEMPTED = True
            try:
                task_id = self._authenticated_client().cards.issue(
                    self._issue_request(), self._private_key()
                )
                self.assertIsNotNone(task_id)
                self._await_card_issue(task_id)
                _CACHED_ISSUE_TASK_ID = task_id
            except Exception as exc:
                _CACHED_ISSUE_ERROR = exc
        if _CACHED_ISSUE_ERROR is not None:
            raise _CACHED_ISSUE_ERROR
        return _CACHED_ISSUE_TASK_ID

    def _private_key(self):
        pem = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCLrBT15MJCcaAh
lv+Z/lTdnyu68ysMV3gqVOINbObUDI2HShcPxjYHu+AReQy03xobKbwMvpNk4x20
zVcAuTTT2KRkSzPwGTmls5TA+n1AZuGRjpUY7T1Bd5YkDf11Kc9qIrPKVm7GzkF9
hRGKVX1q8u0KL/PAb0uRwDOzk+X4vmZmFk5KdDJPFQuhWP/j7RTA7JaY0WC2Bs8e
HcDwKwwggNzRXcIdn89FvqWCxf2aufuiBHr1bPctlzYGxtI/Aq/U4grMWr5u0hwR
B3c0JpUY7jUIirKh3HxOgLK4IEUZmNX2k8Of5n0JSYnOBjNDBCT/Os4roA+dpVmg
h4NUg1XZAgMBAAECggEACjJs4NNbyddLECy6mjLm3fu7CPXsFoVzxs5l5wJEe2Zz
tjT26E5Jn0iseAYZAwL3QFSsj5chwmew4WRs5cb/t/gs70wMvYqP6nyo/2pCNu+T
6AkrcjOOyW7qQZVaY+GCrK5eJydmhMHl5tyuTkXFx2c3HktoLaxKbXiFZcbGT0G2
rI8y19/6PgoBvW5U4PoufdTcDvKZarGajemy40qGZJGscw2vfoMLHhL3vmERacbg
CFcURdU3PzdntsOgJOdT7PcgDVyxgHcew9hpg1vyDhneRuFCr8jDC8KYN9dtAUdT
ODw4bttkJItEbX8zgag2284ZvbJsF65v+a8D20PQUQKBgQDFEmlSfx9W4luZJqcQ
d9qhwTykW68SK17fCNITnx+LToNe0KstainEep6DOEYzt3tKTbkCIbTfeVhOMqRo
YwgZfV045kUZ22CArZ7FBYaut/G2yOPAg5mVpkeIpjC1rK2A9J6zMlwiJ3E75G0J
2nVo+PKdwcnB7LJPuXiSCBBOkQKBgQC1b8ycLWpK+XZAGeohzpxz8qInlHcgLyYC
J0y+kNIOWT1oxqT5iJGA00Rdy+PtV8T5FLmoraavmB7ws41M/6XfJx1JkBAEzx8r
r4llHTe8zZ5MRnxAjArZvAvESZYbzCqwPJTjGvH8qfNhFiQIdrsuw61wCOC6ZNSj
vgHkV5pGyQKBgA25XoRUPgZ69Q4RVwkaj6s8HdEEYYjOZGj74EVli3jUGun7djBP
eGEqeOeCf8ESQg/God+4ITR+6ttnQ3PRkbrUtC1GPAG0+V98t9XYsKxyOu8Txmid
wZBeaBToHfRI9jxIzNSF6UynmoclPUK2Z/7Ld3ntCPPsW+6ZaAAjd59BAoGAZDOk
SrSCOXngJrKpLZaPrTFZAIbr62hek13k8nHEsIv0cEMUpYMY6I7E+RA7hr6sV+ts
RY3xupRGsiRXayjdEIrnj9LyJdXFnzjIpoEmYS0luXZL9NHixDEoRnVlY2C0SrSK
fYpKDoJFmV7C87Gu2rrStEcS5Z3+GZg8L0F6QJECgYAVsEa5JTNCMsz9AKo4/FL4
Alfhyf/W0SbJtgiBeBLJDoEu3+cY6CJ79hndhJFCvcc+aWQAQVZXxscbORoLuoDb
+aJVaQhaniN9sxwd2S6TxzfoTr6HGmsoAYyrKcDi7wSVKfj4PH1P39qRLXVWuWRJ
YSl1QnrMvJj2mvDWk5nntw==
-----END PRIVATE KEY-----"""
        return read_private_key(pem)

    def test_issue_card_from_sandbox(self) -> None:
        self._run_mutations()
        request = self._issue_request()
        self.assertTrue(self._authenticated_client().cards.sign_issue_request(request, self._private_key()))
        try:
            self.assertIsNotNone(self._issue_once())
        except LuminalApiException as exc:
            self.assertIn("signature error", str(exc).lower())

    def test_wait_for_card_open_status_webhook_from_sandbox(self) -> None:
        self._run_mutations()
        try:
            self._await_card_issue(self._issue_once())
        except LuminalApiException as exc:
            self.assertIn("signature error", str(exc).lower())

    def test_list_cards_from_sandbox(self) -> None:
        result = self._authenticated_client().cards.list(
            MemberCardPageRequest(page_no=1, page_size=10, card_type=self._card_type())
        )
        self._assert_page(result)

    def test_get_card_cvv_from_sandbox(self) -> None:
        try:
            result = self._authenticated_client().cards.cvv(
                CardIdRequest(member_card_id=self._first_active_card().member_card_id)
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.member_card_id)
        except LuminalApiException as exc:
            self.assertIn("does not support this operation", str(exc).lower())

    def test_list_card_transactions_from_sandbox(self) -> None:
        result = self._authenticated_client().cards.transactions(
            CardTransactionsRequest(page_no=1, page_size=10, card_type=self._card_type())
        )
        self._assert_page(result)

    def test_get_card_limit_from_sandbox(self) -> None:
        result = self._authenticated_client().cards.limit(
            CardIdRequest(member_card_id=self._first_active_card().member_card_id)
        )
        self.assertIsNotNone(result)
        self.assertTrue(result.member_card_id)

    def test_modify_card_limit_from_sandbox(self) -> None:
        self._run_mutations()
        card = self._first_active_card()
        try:
            result = self._authenticated_client().cards.modify_limit(
                CardLimitUpdateRequest(member_card_id=card.member_card_id, total_limit=card.total_limit + Decimal("1"))
            )
            self.assertIsInstance(result, bool)
        except LuminalApiException as exc:
            self.assertIn("modify limits", str(exc).lower())

    def test_freeze_card_from_sandbox(self) -> None:
        self._run_mutations()
        card_id = self._first_active_card().member_card_id
        client = self._authenticated_client()
        try:
            result = client.cards.freeze(CardIdRequest(member_card_id=card_id))
            self.assertIsInstance(result, bool)
            try:
                webhook = _await_webhook(_CARD_STATUS_WEBHOOKS, card_id, "card status")
                self.assertEqual(str(card_id), str(webhook.member_card_id))
                self.assertEqual("FREEZE", webhook.card_status.upper())
            except TimeoutError:
                page = client.cards.list(
                    MemberCardPageRequest(
                        page_no=1,
                        page_size=1,
                        member_card_id=card_id,
                        card_type=self._card_type(),
                    )
                )
                card = self._first_page_item(page, "cards.list")
                self.assertEqual("FREEZE", card.status.upper())
            second = client.cards.freeze(CardIdRequest(member_card_id=card_id))
            self.assertIsInstance(second, bool)
        except LuminalApiException:
            pass

    def test_unfreeze_card_from_sandbox(self) -> None:
        self._run_mutations()
        card_id = self._first_active_card().member_card_id
        client = self._authenticated_client()
        try:
            client.cards.freeze(CardIdRequest(member_card_id=card_id))
            try:
                webhook = _await_webhook(_CARD_STATUS_WEBHOOKS, card_id, "card status")
                self.assertEqual(str(card_id), str(webhook.member_card_id))
                self.assertEqual("FREEZE", webhook.card_status.upper())
            except TimeoutError:
                page = client.cards.list(
                    MemberCardPageRequest(
                        page_no=1,
                        page_size=1,
                        member_card_id=card_id,
                        card_type=self._card_type(),
                    )
                )
                card = self._first_page_item(page, "cards.list")
                self.assertEqual("FREEZE", card.status.upper())
            result = client.cards.unfreeze(CardIdRequest(member_card_id=card_id))
            self.assertIsInstance(result, bool)
            try:
                webhook = _await_webhook(_CARD_STATUS_WEBHOOKS, card_id, "card status")
                self.assertEqual(str(card_id), str(webhook.member_card_id))
                self.assertEqual("ACTIVE", webhook.card_status.upper())
            except TimeoutError:
                page = client.cards.list(
                    MemberCardPageRequest(
                        page_no=1,
                        page_size=1,
                        member_card_id=card_id,
                        card_type=self._card_type(),
                    )
                )
                card = self._first_page_item(page, "cards.list")
                self.assertEqual("ACTIVE", card.status.upper())
            second = client.cards.unfreeze(CardIdRequest(member_card_id=card_id))
            self.assertIsInstance(second, bool)
        except LuminalApiException:
            pass

    def test_cancel_card_from_sandbox(self) -> None:
        self._run_destructive_mutations()
        card_id = self._first_active_card().member_card_id
        try:
            result = self._authenticated_client().cards.cancel(
                CardIdRequest(member_card_id=card_id)
            )
            self.assertIsInstance(result, bool)
            try:
                webhook = _await_webhook(_CARD_STATUS_WEBHOOKS, card_id, "card status")
                self.assertEqual(str(card_id), str(webhook.member_card_id))
                self.assertEqual("CANCEL", webhook.card_status.upper())
            except TimeoutError:
                page = self._authenticated_client().cards.list(
                    MemberCardPageRequest(
                        page_no=1,
                        page_size=1,
                        member_card_id=card_id,
                        card_type=self._card_type(),
                    )
                )
                card = self._first_page_item(page, "cards.list")
                self.assertEqual("CANCEL", card.status.upper())
        except LuminalApiException as exc:
            self.assertIn("cancel", str(exc).lower())

    def test_get_card_issue_details_from_sandbox(self) -> None:
        self._run_mutations()
        try:
            task_id = self._issue_once()
            self.assertIsNotNone(task_id)
            result = self._authenticated_client().cards.issue_details(IssueCardDetailsRequest(task_id=task_id))
            self.assertIsNotNone(result)
            self.assertIsInstance(result, list)
        except LuminalApiException as exc:
            self.assertIn("signature error", str(exc).lower())


class SandboxCardGroupsApiTest(_SandboxIntegrationTestCase):
    def _card_type(self) -> str:
        return os.getenv("LUMINAL_OPEN_API_CARD_TYPE", "SHARED")

    def test_list_card_groups_from_sandbox(self) -> None:
        result = self._authenticated_client().card_groups.list(
            CardGroupRequest(page_no=1, page_size=10, card_type=self._card_type())
        )
        self._assert_page(result)

    def test_create_card_group_from_sandbox(self) -> None:
        self._run_mutations()
        self.assertTrue(self._created_card_group().card_group_id)

    def test_update_card_group_from_sandbox(self) -> None:
        self._run_mutations()
        result = self._authenticated_client().card_groups.update(
            CardGroupUpdateRequest(
                card_group_id=self._created_card_group().card_group_id,
                card_group_name="updated-group",
            )
        )
        self.assertIsInstance(result, bool)

    def test_delete_card_group_from_sandbox(self) -> None:
        self._run_destructive_mutations()
        result = self._authenticated_client().card_groups.delete(
            CardGroupDeleteRequest(card_group_id=self._delete_card_group().card_group_id)
        )
        self.assertIsInstance(result, bool)


_TEST_ORDER = (
    (SandboxAuthApiTest, "test_get_token_from_sandbox"),
    (SandboxAuthApiTest, "test_refresh_token_from_sandbox"),
    (SandboxAuthApiTest, "test_logout_from_sandbox"),
    (SandboxAuthApiTest, "test_get_token_after_logout_from_sandbox"),
    (SandboxSharedAccountsApiTest, "test_create_shared_account_from_sandbox"),
    (SandboxCardGroupsApiTest, "test_create_card_group_from_sandbox"),
    (SandboxSharedAccountsApiTest, "test_increase_shared_account_from_sandbox"),
    (SandboxCardsApiTest, "test_issue_card_from_sandbox"),
    (SandboxCardsApiTest, "test_wait_for_card_open_status_webhook_from_sandbox"),
    (SandboxSharedAccountsApiTest, "test_decrease_shared_account_from_sandbox"),
    (SandboxAccountsApiTest, "test_list_accounts_from_sandbox"),
    (SandboxTransactionsApiTest, "test_list_transactions_from_sandbox"),
    (SandboxSharedAccountsApiTest, "test_list_shared_accounts_from_sandbox"),
    (SandboxSharedAccountsApiTest, "test_get_shared_account_details_from_sandbox"),
    (SandboxSharedAccountsApiTest, "test_list_shared_account_transactions_from_sandbox"),
    (SandboxCardsApiTest, "test_list_cards_from_sandbox"),
    (SandboxCardsApiTest, "test_get_card_cvv_from_sandbox"),
    (SandboxCardsApiTest, "test_list_card_transactions_from_sandbox"),
    (SandboxCardsApiTest, "test_get_card_limit_from_sandbox"),
    (SandboxCardsApiTest, "test_modify_card_limit_from_sandbox"),
    (SandboxCardsApiTest, "test_get_card_issue_details_from_sandbox"),
    (SandboxCardGroupsApiTest, "test_list_card_groups_from_sandbox"),
    (SandboxCardGroupsApiTest, "test_update_card_group_from_sandbox"),
    (SandboxCardsApiTest, "test_freeze_card_from_sandbox"),
    (SandboxCardsApiTest, "test_unfreeze_card_from_sandbox"),
    (SandboxCardsApiTest, "test_cancel_card_from_sandbox"),
    (SandboxCardGroupsApiTest, "test_delete_card_group_from_sandbox"),
)

assert tuple(
    test_name for test_class, test_name in _TEST_ORDER if test_class is SandboxCardsApiTest
) == (
    "test_issue_card_from_sandbox",
    "test_wait_for_card_open_status_webhook_from_sandbox",
    "test_list_cards_from_sandbox",
    "test_get_card_cvv_from_sandbox",
    "test_list_card_transactions_from_sandbox",
    "test_get_card_limit_from_sandbox",
    "test_modify_card_limit_from_sandbox",
    "test_get_card_issue_details_from_sandbox",
    "test_freeze_card_from_sandbox",
    "test_unfreeze_card_from_sandbox",
    "test_cancel_card_from_sandbox",
)


def load_tests(loader, tests, pattern):
    """Match the Java SDK integration-test order instead of unittest name sorting."""
    return unittest.TestSuite(test_class(test_name) for test_class, test_name in _TEST_ORDER)


if __name__ == "__main__":
    unittest.main()
