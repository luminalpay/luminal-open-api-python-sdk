"""Real HTTP integration tests for the recharge-card Luminal Open API flow.

The recharge-card flow is intentionally independent from the shared-card flow so it
can be run by itself with its own card BIN, card group, operation records, and
webhook correlation. Configure the recharge-card credentials before running this
module; the module is skipped when they are not present.
"""

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
from dataclasses import replace
from datetime import date
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from luminal_open_api_sdk import (
    CardBinsRequest,
    CardGroupCreateRequest,
    CardHolderCardPageRequest,
    CardHolderCreateRequest,
    CardHolderModifyRequest,
    CardHolderPageRequest,
    CardIdRequest,
    CardLimitUpdateRequest,
    CardOpenStatusWebhook,
    CardStatusWebhook,
    CardTransactionsRequest,
    IssueCardDetailsRequest,
    IssueCardRequest,
    LuminalApiException,
    LuminalOpenApiClient,
    MemberCardPageRequest,
    MemberCardRechargeRequest,
    MemberCardWithdrawRequest,
    RechargeCardOperationRecordRequest,
    RechargeCardOperationRecordResponse,
    RechargeCardTransferStatusWebhook,
    TransactionWebhook,
    WebhookEventType,
    read_private_key,
)
from tests.support import SANDBOX_WEBHOOK_PUBLIC_KEY_PEM


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


DEFAULT_BASE_URL = "https://sandbox-openapi.luminalads.com"
DEFAULT_CARD_BIN = "578391"
DEFAULT_WEBHOOK_HOST = "0.0.0.0"
DEFAULT_WEBHOOK_PORT = 18082
DEFAULT_WEBHOOK_PATH = "/luminal-open-api-webhook"
DEFAULT_WEBHOOK_WAIT_SECONDS = 30.0
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
MAX_WEBHOOK_BODY_BYTES = 1024 * 1024
CURRENT_CARD_TYPE = "RECHARGE"
LIMIT_OPERATION_TYPE = "MODIFY_LIMITS"

_LOGGER = logging.getLogger(__name__)
_WEBHOOK_CONDITION = threading.Condition()
_CARD_OPEN_WEBHOOKS: dict[str, CardOpenStatusWebhook] = {}
_CARD_STATUS_WEBHOOKS: dict[str, CardStatusWebhook] = {}
_TRANSFER_WEBHOOKS: dict[str, RechargeCardTransferStatusWebhook] = {}
_TRANSACTION_WEBHOOKS: dict[str, TransactionWebhook] = {}
_SETTLEMENT_WEBHOOKS: dict[str, TransactionWebhook] = {}
_WEBHOOK_ERROR: Exception | None = None
_WEBHOOK_SERVER: ThreadingHTTPServer | None = None
_WEBHOOK_THREAD: threading.Thread | None = None
_CACHED_CLIENT: LuminalOpenApiClient | None = None
_CACHED_PUBLIC_CLIENT: LuminalOpenApiClient | None = None
_CACHED_CARD_BIN: Any = None
_CACHED_CARD_GROUP: Any = None
_CACHED_CARDHOLDER_TEMPLATE: Any = None
_CACHED_CARDHOLDER_COUNTRIES: list[Any] | None = None
_CACHED_CARDHOLDER_ID: int | None = None
_CACHED_ISSUE_TASK_ID: int | None = None
_CACHED_CARD_ID: int | None = None
_CACHED_LIMIT_OPERATION_ID: int | None = None
_CACHED_RECHARGE_OPERATION_ID: int | None = None
_CACHED_WITHDRAW_OPERATION_ID: int | None = None
_SANDBOX_URLOPEN = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
).open


def _configured(primary: str, fallback: str | None = None, default: str | None = None) -> str | None:
    for name in (primary, fallback):
        if name is None:
            continue
        value = os.getenv(name)
        if value is not None and value.strip():
            return value
    return default


def _configured_int(primary: str, fallback: str | None, default: int | None = None) -> int | None:
    value = _configured(primary, fallback, None if default is None else str(default))
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{primary} must be an integer") from exc


def _configured_decimal(primary: str, fallback: str | None, default: str) -> Decimal:
    value = _configured(primary, fallback, default)
    try:
        return Decimal(value or default)
    except ArithmeticError as exc:
        raise ValueError(f"{primary} must be a decimal") from exc


def _sandbox_urlopen(
    request: Any,
    *,
    timeout: float,
    _urlopen: Any = _SANDBOX_URLOPEN,
    _sleep: Any = time.sleep,
) -> Any:
    """Retry only TLS handshake EOFs, before the HTTP request is sent."""

    for attempt in range(3):
        try:
            return _urlopen(request, timeout=timeout)
        except urllib.error.URLError as exc:
            if attempt == 2 or not isinstance(exc.reason, ssl.SSLEOFError):
                raise
            _sleep(0.2)
    raise AssertionError("unreachable")


def _normalize_path(value: str) -> str:
    return value if value.startswith("/") else "/" + value


def _webhook_path() -> str:
    return RechargeCardSandboxOpenApiIntegrationTest._webhook_path()


def _webhook_host() -> str:
    return RechargeCardSandboxOpenApiIntegrationTest._webhook_host()


def _webhook_port() -> int:
    return RechargeCardSandboxOpenApiIntegrationTest._webhook_port()


def _record_webhook(event_type: WebhookEventType, payload: Any) -> None:
    with _WEBHOOK_CONDITION:
        if event_type is WebhookEventType.CARD_OPEN_STATUS:
            results = payload.list
            if results and all(item.card_status in {"SUCCESS", "FAIL"} for item in results):
                _CARD_OPEN_WEBHOOKS[str(payload.card_apply_task_id)] = payload
        elif event_type is WebhookEventType.CARD_STATUS:
            _CARD_STATUS_WEBHOOKS[str(payload.member_card_id)] = payload
        elif event_type in {
            WebhookEventType.CARD_RECHARGE_STATUS,
            WebhookEventType.CARD_WITHDRAW_STATUS,
            WebhookEventType.CARD_LIMIT_STATUS,
        }:
            if payload.status in {"SUCCESS", "FAIL"}:
                _TRANSFER_WEBHOOKS[str(payload.member_card_operation_record_id)] = payload
        elif event_type is WebhookEventType.CARD_TRANSACTIONS:
            _TRANSACTION_WEBHOOKS[str(payload.member_card_id)] = payload
        elif event_type is WebhookEventType.CARD_SETTLE_STATUS:
            _SETTLEMENT_WEBHOOKS[str(payload.member_card_transaction_id)] = payload
        _WEBHOOK_CONDITION.notify_all()


def _record_webhook_error(exc: Exception) -> None:
    global _WEBHOOK_ERROR
    with _WEBHOOK_CONDITION:
        if _WEBHOOK_ERROR is None:
            _WEBHOOK_ERROR = exc
        _WEBHOOK_CONDITION.notify_all()


class _WebhookRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != _webhook_path():
            self._respond(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", ""))
            if content_length < 0 or content_length > MAX_WEBHOOK_BODY_BYTES:
                self._respond(413)
                return
        except ValueError:
            self._respond(400)
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._respond(400)
            return
        event_name = self.headers.get("event", "")
        try:
            event_type = WebhookEventType(event_name)
        except ValueError:
            self._respond(200)
            return
        supported = {
            WebhookEventType.CARD_OPEN_STATUS,
            WebhookEventType.CARD_STATUS,
            WebhookEventType.CARD_RECHARGE_STATUS,
            WebhookEventType.CARD_WITHDRAW_STATUS,
            WebhookEventType.CARD_LIMIT_STATUS,
            WebhookEventType.CARD_TRANSACTIONS,
            WebhookEventType.CARD_SETTLE_STATUS,
        }
        if event_type not in supported:
            self._respond(200)
            return
        try:
            public_key = RechargeCardSandboxOpenApiIntegrationTest._webhook_public_key()
            event = LuminalOpenApiClient(
                RechargeCardSandboxOpenApiIntegrationTest._base_url(),
                log_http=os.getenv("LUMINAL_OPEN_API_LOG_HTTP", "1") == "1",
                log_raw_http=os.getenv("LUMINAL_OPEN_API_LOG_RAW_HTTP", "1") == "1",
            ).parse_webhook(
                event_type,
                self.headers.get("event_id", ""),
                body,
                self.headers.get("sign", ""),
                public_key,
            )
            _record_webhook(event_type, event.payload)
        except Exception as exc:
            _record_webhook_error(exc)
            self._respond(400)
            return
        self._respond(200)

    def do_GET(self) -> None:
        self._respond(405)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _respond(self, status: int) -> None:
        body = b"ok" if status == 200 else b""
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)


def setUpModule() -> None:
    global _WEBHOOK_SERVER, _WEBHOOK_THREAD
    if not RechargeCardSandboxOpenApiIntegrationTest._sandbox_enabled():
        return
    host = _webhook_host()
    port = _webhook_port()
    _WEBHOOK_SERVER = ThreadingHTTPServer((host, port), _WebhookRequestHandler)
    _WEBHOOK_SERVER.daemon_threads = True
    _WEBHOOK_THREAD = threading.Thread(
        target=_WEBHOOK_SERVER.serve_forever,
        name="recharge-card-sandbox-webhook",
        daemon=True,
    )
    _WEBHOOK_THREAD.start()
    _LOGGER.info("recharge-card webhook listener on %s:%s%s", host, port, _webhook_path())


def tearDownModule() -> None:
    if _WEBHOOK_SERVER is not None:
        _WEBHOOK_SERVER.shutdown()
        _WEBHOOK_SERVER.server_close()
    if _WEBHOOK_THREAD is not None:
        _WEBHOOK_THREAD.join(timeout=5)


def _await_webhook(store: dict[str, Any], key: Any, operation: str) -> Any:
    started = time.monotonic()
    deadline = started + RechargeCardSandboxOpenApiIntegrationTest._webhook_wait_seconds()
    next_log = started + 10.0
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
            wait_for = min(remaining, max(0.0, next_log - time.monotonic()))
            _WEBHOOK_CONDITION.wait(wait_for)
            if time.monotonic() >= next_log:
                _LOGGER.info(
                    "waiting for %s, elapsed=%ds",
                    operation,
                    int(time.monotonic() - started),
                )
                next_log = time.monotonic() + 10.0


def _is_final_status(status: str | None) -> bool:
    return isinstance(status, str) and status.upper() in {"SUCCESS", "FAIL"}


def _is_failed_card_status(status: str | None) -> bool:
    return isinstance(status, str) and status.upper() in {
        "FAIL",
        "CANCEL",
        "RISK_CANCEL",
        "ADMIN_CANCEL",
    }


class RechargeCardSandboxOpenApiIntegrationTest(unittest.TestCase):
    """Ordered end-to-end tests for the recharge-card Sandbox flow."""

    BASE_URL = DEFAULT_BASE_URL
    APP_ID = "lpsha6pj5mwsb7tz"
    APP_SECRET = "P11g59PXY33JjqL4CRJ2Oz3nfsjsWRKe"
    CARD_BIN = DEFAULT_CARD_BIN
    WEBHOOK_HOST = DEFAULT_WEBHOOK_HOST
    WEBHOOK_PORT = DEFAULT_WEBHOOK_PORT
    WEBHOOK_PATH = DEFAULT_WEBHOOK_PATH
    WEBHOOK_WAIT_SECONDS = DEFAULT_WEBHOOK_WAIT_SECONDS
    POLL_INTERVAL_SECONDS = DEFAULT_POLL_INTERVAL_SECONDS
    WEBHOOK_PUBLIC_KEY = SANDBOX_WEBHOOK_PUBLIC_KEY_PEM
    PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
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

    @classmethod
    def _sandbox_enabled(cls) -> bool:
        return bool(cls._app_id() and cls._app_secret())

    @classmethod
    def _base_url(cls) -> str:
        return _configured(
            "LUMINAL_OPEN_API_RECHARGE_BASE_URL",
            "LUMINAL_OPEN_API_BASE_URL",
            cls.BASE_URL,
        ) or cls.BASE_URL

    @classmethod
    def _app_id(cls) -> str:
        return _configured(
            "LUMINAL_OPEN_API_RECHARGE_APP_ID",
            "LUMINAL_OPEN_API_APP_ID",
            cls.APP_ID,
        ) or cls.APP_ID

    @classmethod
    def _app_secret(cls) -> str:
        return _configured(
            "LUMINAL_OPEN_API_RECHARGE_APP_SECRET",
            "LUMINAL_OPEN_API_APP_SECRET",
            cls.APP_SECRET,
        ) or cls.APP_SECRET

    @classmethod
    def _webhook_path(cls) -> str:
        return _normalize_path(
            _configured(
                "LUMINAL_OPEN_API_RECHARGE_WEBHOOK_PATH",
                "LUMINAL_OPEN_API_WEBHOOK_PATH",
                cls.WEBHOOK_PATH,
            )
            or cls.WEBHOOK_PATH
        )

    @classmethod
    def _webhook_host(cls) -> str:
        return _configured(
            "LUMINAL_OPEN_API_RECHARGE_WEBHOOK_HOST",
            "LUMINAL_OPEN_API_WEBHOOK_HOST",
            cls.WEBHOOK_HOST,
        ) or cls.WEBHOOK_HOST

    @classmethod
    def _webhook_port(cls) -> int:
        return _configured_int(
            "LUMINAL_OPEN_API_RECHARGE_WEBHOOK_PORT",
            "LUMINAL_OPEN_API_WEBHOOK_PORT",
            cls.WEBHOOK_PORT,
        ) or cls.WEBHOOK_PORT

    @classmethod
    def _webhook_wait_seconds(cls) -> float:
        return float(
            _configured(
                "LUMINAL_OPEN_API_RECHARGE_WEBHOOK_TIMEOUT_SECONDS",
                "LUMINAL_OPEN_API_WEBHOOK_TIMEOUT_SECONDS",
                str(cls.WEBHOOK_WAIT_SECONDS),
            )
            or cls.WEBHOOK_WAIT_SECONDS
        )

    @classmethod
    def _poll_interval_seconds(cls) -> float:
        return float(
            _configured(
                "LUMINAL_OPEN_API_RECHARGE_POLL_INTERVAL_SECONDS",
                "LUMINAL_OPEN_API_POLL_INTERVAL_SECONDS",
                str(cls.POLL_INTERVAL_SECONDS),
            )
            or cls.POLL_INTERVAL_SECONDS
        )

    @classmethod
    def _webhook_public_key(cls) -> str:
        return (
            _configured(
                "LUMINAL_OPEN_API_RECHARGE_WEBHOOK_PUBLIC_KEY",
                "LUMINAL_OPEN_API_WEBHOOK_PUBLIC_KEY",
                cls.WEBHOOK_PUBLIC_KEY,
            )
            or cls.WEBHOOK_PUBLIC_KEY
        ).replace("\\n", "\n")

    def _client(self) -> LuminalOpenApiClient:
        global _CACHED_CLIENT
        if _CACHED_CLIENT is None:
            _CACHED_CLIENT = LuminalOpenApiClient(
                self._base_url(),
                timeout=float(os.getenv("LUMINAL_OPEN_API_TIMEOUT", "15")),
                app_id=self._app_id(),
                app_secret=self._app_secret(),
                retry_unauthorized=int(os.getenv("LUMINAL_OPEN_API_RETRY_UNAUTHORIZED", "1")),
                accept_language=os.getenv("LUMINAL_OPEN_API_ACCEPT_LANGUAGE", "en"),
                log_http=os.getenv("LUMINAL_OPEN_API_LOG_HTTP", "1") == "1",
                log_raw_http=os.getenv("LUMINAL_OPEN_API_LOG_RAW_HTTP", "1") == "1",
                opener=_sandbox_urlopen,
            )
        return _CACHED_CLIENT

    def _public_client(self) -> LuminalOpenApiClient:
        global _CACHED_PUBLIC_CLIENT
        if _CACHED_PUBLIC_CLIENT is None:
            _CACHED_PUBLIC_CLIENT = LuminalOpenApiClient(
                self._base_url(),
                timeout=float(os.getenv("LUMINAL_OPEN_API_TIMEOUT", "15")),
                log_http=os.getenv("LUMINAL_OPEN_API_LOG_HTTP", "1") == "1",
                log_raw_http=os.getenv("LUMINAL_OPEN_API_LOG_RAW_HTTP", "1") == "1",
                opener=_sandbox_urlopen,
            )
        return _CACHED_PUBLIC_CLIENT

    def _assert_page(self, page: Any) -> None:
        self.assertIsNotNone(page)
        self.assertIsInstance(page.list, list)

    def _first_page_item(self, page: Any, label: str) -> Any:
        self._assert_page(page)
        self.assertTrue(page.list, f"{label} returned no rows")
        return page.list[0]

    def _card_bin_name(self) -> str:
        return _configured(
            "LUMINAL_OPEN_API_RECHARGE_CARD_BIN",
            "LUMINAL_OPEN_API_CARD_BIN",
            self.CARD_BIN,
        ) or self.CARD_BIN

    def _first_recharge_card_bin(self) -> Any:
        global _CACHED_CARD_BIN
        if _CACHED_CARD_BIN is None:
            page = self._client().cards.bins(
                CardBinsRequest(
                    page_no=1,
                    page_size=50,
                    card_type=CURRENT_CARD_TYPE,
                    card_bin=self._card_bin_name(),
                )
            )
            self._assert_page(page)
            _CACHED_CARD_BIN = next(
                (item for item in page.list if str(item.card_bin) == self._card_bin_name()),
                None,
            )
            self.assertIsNotNone(_CACHED_CARD_BIN, f"recharge card BIN {self._card_bin_name()} not found")
            self.assertIsNotNone(_CACHED_CARD_BIN.card_bin_id)
        return _CACHED_CARD_BIN

    def _supports_custom_cardholder(self) -> bool:
        return getattr(self._first_recharge_card_bin(), "custom_cardholder", None) == 1

    def _supports_card_limit(self) -> bool:
        return getattr(self._first_recharge_card_bin(), "can_limit", None) == 1

    def _ensure_recharge_card_group(self) -> Any:
        global _CACHED_CARD_GROUP
        if _CACHED_CARD_GROUP is None:
            _CACHED_CARD_GROUP = self._client().card_groups.create(
                CardGroupCreateRequest(
                    card_group_name=f"sdk-sandbox-recharge-{uuid.uuid4().hex[:12]}",
                    card_type=CURRENT_CARD_TYPE,
                )
            )
        self.assertIsNotNone(_CACHED_CARD_GROUP)
        self.assertTrue(_CACHED_CARD_GROUP.card_group_id)
        return _CACHED_CARD_GROUP

    def _cardholder_countries(self) -> list[Any]:
        global _CACHED_CARDHOLDER_COUNTRIES
        if _CACHED_CARDHOLDER_COUNTRIES is None:
            countries = self._client().card_holders.countries()
            self.assertIsNotNone(countries)
            self.assertTrue(countries)
            _CACHED_CARDHOLDER_COUNTRIES = countries
        return _CACHED_CARDHOLDER_COUNTRIES

    def _existing_cardholder_template(self) -> Any:
        global _CACHED_CARDHOLDER_TEMPLATE
        if _CACHED_CARDHOLDER_TEMPLATE is not None:
            return _CACHED_CARDHOLDER_TEMPLATE
        page = self._client().card_holders.page(CardHolderPageRequest(page_no=1, page_size=1))
        self._assert_page(page)
        if not page.list:
            return None
        holder_id = page.list[0].card_holder_id
        _CACHED_CARDHOLDER_TEMPLATE = self._client().card_holders.detail(holder_id)
        return _CACHED_CARDHOLDER_TEMPLATE

    def _selected_cardholder_country(self, template: Any) -> Any:
        countries = self._cardholder_countries()
        configured_id = _configured_int(
            "LUMINAL_OPEN_API_CARD_HOLDER_COUNTRY_ID",
            "LUMINAL_OPEN_API_RECHARGE_CARD_HOLDER_COUNTRY_ID",
        )
        configured_area = _configured(
            "LUMINAL_OPEN_API_CARD_HOLDER_AREA_CODE",
            "LUMINAL_OPEN_API_RECHARGE_CARD_HOLDER_AREA_CODE",
        )
        if configured_id is not None:
            country = next((item for item in countries if item.country_id == configured_id), None)
            self.assertIsNotNone(country, f"cardholder country {configured_id} was not returned")
            if configured_area is not None:
                self.assertEqual(configured_area, country.area_code)
            return country
        if configured_area is not None:
            matches = [item for item in countries if item.area_code == configured_area]
            self.assertEqual(1, len(matches), f"area code {configured_area} must match one country")
            return matches[0]
        if template is not None and template.country_id is not None:
            country = next((item for item in countries if item.country_id == template.country_id), None)
            if country is not None:
                return country
        return next(
            (item for item in countries if str(item.country_code).upper() == "HK"),
            countries[0],
        )

    @staticmethod
    def _local_phone(country: Any, suffix: int) -> str:
        length = country.phone_max_length
        if not isinstance(length, int) or length <= 0:
            raise AssertionError(f"country {country.country_id} has invalid phoneMaxLength")
        seed = str(suffix % 1_000_000)
        return ("5" + seed * (length + 1))[:length]

    def _cardholder_profile(self, address_line2: str) -> CardHolderCreateRequest:
        template = self._existing_cardholder_template()
        country = self._selected_cardholder_country(template)
        suffix = int(time.time() * 1000) % 1_000_000
        return CardHolderCreateRequest(
            last_name="Sdk",
            first_name=f"Sandbox{suffix % 26:02d}",
            birth_date=date(1990, 1, 15),
            mail=f"sdk-recharge-{suffix}@example.com",
            phone=self._local_phone(country, suffix),
            area_code=country.area_code,
            country_id=country.country_id,
            postal_code=getattr(template, "postal_code", None) or "10001",
            state=getattr(template, "state", None) or "New York",
            city=getattr(template, "city", None) or "New York",
            address_line1=getattr(template, "address_line1", None) or "350 Fifth Avenue",
            address_line2=address_line2,
        )

    def _ensure_cardholder_id(self) -> int:
        global _CACHED_CARDHOLDER_ID, _CACHED_CARDHOLDER_TEMPLATE
        if _CACHED_CARDHOLDER_ID is None:
            template = self._existing_cardholder_template()
            if template is not None and template.card_holder_id is not None:
                _CACHED_CARDHOLDER_ID = template.card_holder_id
            else:
                _CACHED_CARDHOLDER_ID = self._client().card_holders.add(
                    self._cardholder_profile("Created by Python SDK Sandbox test")
                )
                self.assertIsNotNone(_CACHED_CARDHOLDER_ID)
                _CACHED_CARDHOLDER_TEMPLATE = self._client().card_holders.detail(_CACHED_CARDHOLDER_ID)
        self.assertTrue(_CACHED_CARDHOLDER_ID)
        return _CACHED_CARDHOLDER_ID

    def _modify_request(self, profile: Any, *, address_line2: str, phone: str | None = None) -> CardHolderModifyRequest:
        return CardHolderModifyRequest(
            card_holder_id=profile.card_holder_id,
            last_name=profile.last_name,
            first_name=profile.first_name,
            birth_date=profile.birth_date,
            mail=profile.mail,
            phone=profile.phone if phone is None else phone,
            area_code=profile.area_code,
            country_id=profile.country_id,
            postal_code=profile.postal_code,
            state=profile.state,
            city=profile.city,
            address_line1=profile.address_line1,
            address_line2=address_line2,
        )

    def _private_key(self) -> Any:
        pem = _configured(
            "LUMINAL_OPEN_API_RECHARGE_PRIVATE_KEY",
            "LUMINAL_OPEN_API_PRIVATE_KEY",
        )
        path = _configured(
            "LUMINAL_OPEN_API_RECHARGE_PRIVATE_KEY_PATH",
            "LUMINAL_OPEN_API_PRIVATE_KEY_PATH",
        )
        if pem:
            return read_private_key(pem.replace("\\n", "\n"))
        if path:
            with open(path, encoding="utf-8") as stream:
                return read_private_key(stream.read())
        return read_private_key(self.PRIVATE_KEY.replace("\\n", "\n"))

    def _issue_task_id(self) -> int:
        global _CACHED_ISSUE_TASK_ID
        if _CACHED_ISSUE_TASK_ID is None:
            configured_task = _configured_int(
                "LUMINAL_OPEN_API_RECHARGE_ISSUE_TASK_ID",
                "LUMINAL_OPEN_API_ISSUE_TASK_ID",
            )
            if configured_task is not None:
                _CACHED_ISSUE_TASK_ID = configured_task
            else:
                card_bin = self._first_recharge_card_bin()
                holder_id = self._ensure_cardholder_id() if self._supports_custom_cardholder() else None
                request = IssueCardRequest(
                    apply_count=1,
                    card_bin_id=card_bin.card_bin_id,
                    card_group_id=self._ensure_recharge_card_group().card_group_id,
                    card_name=_configured(
                        "LUMINAL_OPEN_API_RECHARGE_ISSUE_CARD_NAME",
                        "LUMINAL_OPEN_API_ISSUE_CARD_NAME",
                        f"sdk-sandbox-recharge-{uuid.uuid4().hex[:12]}",
                    ),
                    card_type=CURRENT_CARD_TYPE,
                    member_shared_account_id=None,
                    daily_limit=_configured_decimal(
                        "LUMINAL_OPEN_API_RECHARGE_DAILY_LIMIT",
                        None,
                        "100.00",
                    ),
                    month_limit=_configured_decimal(
                        "LUMINAL_OPEN_API_RECHARGE_MONTH_LIMIT",
                        None,
                        "1000.00",
                    ),
                    recharge_amount=_configured_decimal(
                        "LUMINAL_OPEN_API_RECHARGE_ISSUE_AMOUNT",
                        None,
                        "10.00",
                    ),
                    card_holder_id=holder_id,
                )
                _CACHED_ISSUE_TASK_ID = self._client().cards.issue(request, self._private_key())
                self.assertIsNotNone(_CACHED_ISSUE_TASK_ID)
        self.assertTrue(_CACHED_ISSUE_TASK_ID)
        return _CACHED_ISSUE_TASK_ID

    def _card_id_from_open_webhook(self, task_id: int, payload: CardOpenStatusWebhook) -> int:
        self.assertEqual(str(task_id), str(payload.card_apply_task_id))
        result = next((item for item in (payload.list or []) if item.member_card_id), None)
        self.assertIsNotNone(result, "CARD_OPEN_STATUS webhook contains no card result")
        self.assertEqual("SUCCESS", result.card_status, result.message)
        return result.member_card_id

    def _card_id_from_issue_details(self, task_id: int, timeout: BaseException) -> int:
        deadline = time.monotonic() + self._webhook_wait_seconds()
        while time.monotonic() < deadline:
            details = self._client().cards.issue_details(IssueCardDetailsRequest(task_id=task_id))
            result = next(
                (
                    item
                    for item in (details or [])
                    if item.member_card_id and item.card_status and item.card_status.upper() != "APPLYING"
                ),
                None,
            )
            if result is not None:
                if _is_failed_card_status(result.card_status):
                    self.fail(f"recharge-card opening failed: {result.card_status}, {result.message}")
                return result.member_card_id
            time.sleep(self._poll_interval_seconds())
        raise AssertionError(f"CARD_OPEN_STATUS timed out for task {task_id}") from timeout

    def _ensure_recharge_card_id(self) -> int:
        global _CACHED_CARD_ID
        if _CACHED_CARD_ID is None:
            configured_card = _configured_int(
                "LUMINAL_OPEN_API_RECHARGE_CARD_ID",
                "LUMINAL_OPEN_API_CARD_ID",
            )
            if configured_card is not None:
                _CACHED_CARD_ID = configured_card
            else:
                task_id = self._issue_task_id()
                try:
                    payload = _await_webhook(_CARD_OPEN_WEBHOOKS, task_id, "CARD_OPEN_STATUS")
                    _CACHED_CARD_ID = self._card_id_from_open_webhook(task_id, payload)
                except TimeoutError as exc:
                    _CACHED_CARD_ID = self._card_id_from_issue_details(task_id, exc)
        self.assertTrue(_CACHED_CARD_ID)
        return _CACHED_CARD_ID

    def _validate_transfer(
        self,
        operation_id: int,
        expected_type: str,
        actual: RechargeCardTransferStatusWebhook | RechargeCardOperationRecordResponse,
    ) -> None:
        self.assertEqual(str(operation_id), str(actual.member_card_operation_record_id))
        self.assertEqual(CURRENT_CARD_TYPE, str(actual.card_type).upper())
        self.assertEqual(str(self._ensure_recharge_card_id()), str(actual.member_card_id))
        self.assertEqual(expected_type, str(actual.operation_type).upper())
        self.assertNotEqual("FAIL", str(actual.status).upper(), getattr(actual, "message", None))

    def _operation_from_webhook(
        self, payload: RechargeCardTransferStatusWebhook
    ) -> RechargeCardOperationRecordResponse:
        return RechargeCardOperationRecordResponse(
            member_card_operation_record_id=payload.member_card_operation_record_id,
            member_card_id=payload.member_card_id,
            card_type=payload.card_type,
            operation_type=payload.operation_type,
            amount=payload.amount,
            currency_code=payload.currency_code,
            balance=payload.balance,
            status=payload.status,
            message=payload.message,
            update_time=None,
        )

    def _await_operation(self, operation_id: int, expected_type: str) -> RechargeCardOperationRecordResponse:
        try:
            payload = _await_webhook(
                _TRANSFER_WEBHOOKS,
                operation_id,
                f"{expected_type} operationRecordId={operation_id}",
            )
            self._validate_transfer(operation_id, expected_type, payload)
            return self._operation_from_webhook(payload)
        except TimeoutError as timeout:
            deadline = time.monotonic() + self._webhook_wait_seconds()
            while time.monotonic() < deadline:
                result = self._client().cards.operation_record(
                    RechargeCardOperationRecordRequest(operation_id)
                )
                if result is not None and _is_final_status(result.status):
                    self._validate_transfer(operation_id, expected_type, result)
                    return result
                time.sleep(self._poll_interval_seconds())
            self.fail(f"{expected_type} operation did not reach a final state")
            raise AssertionError("unreachable") from timeout

    def _clear_card_status(self, card_id: int) -> None:
        with _WEBHOOK_CONDITION:
            _CARD_STATUS_WEBHOOKS.pop(str(card_id), None)

    def _current_card_status(self, card_id: int) -> str:
        page = self._client().cards.list(
            MemberCardPageRequest(
                page_no=1,
                page_size=1,
                member_card_id=card_id,
                card_type=CURRENT_CARD_TYPE,
            )
        )
        card = self._first_page_item(page, "cards.list")
        return str(card.status)

    def _await_card_status(self, card_id: int, expected: str) -> None:
        try:
            payload = _await_webhook(_CARD_STATUS_WEBHOOKS, card_id, "CARD_STATUS")
            self.assertEqual(str(card_id), str(payload.member_card_id))
            self.assertEqual(expected, str(payload.card_status).upper())
            return
        except TimeoutError:
            deadline = time.monotonic() + self._webhook_wait_seconds()
            while time.monotonic() < deadline:
                if expected == self._current_card_status(card_id).upper():
                    return
                time.sleep(self._poll_interval_seconds())
        self.fail(f"card {card_id} did not reach status {expected}")

    def test_get_token_from_sandbox(self) -> None:
        token = self._public_client().auth.get_token(self._app_id(), self._app_secret())
        self.assertIsNotNone(token)
        self.assertTrue(token.access_token)

    def test_list_recharge_card_bins_from_sandbox(self) -> None:
        self.assertTrue(self._first_recharge_card_bin().card_bin_id)

    def test_create_recharge_card_group_from_sandbox(self) -> None:
        self.assertTrue(self._ensure_recharge_card_group().card_group_id)

    def test_list_cardholder_countries_from_sandbox(self) -> None:
        country = self._selected_cardholder_country(self._existing_cardholder_template())
        self.assertTrue(country.country_id)
        self.assertTrue(country.area_code)
        self.assertGreater(country.phone_max_length, 0)

    def test_create_cardholder_rejects_blank_phone_from_sandbox(self) -> None:
        profile = self._cardholder_profile("Invalid blank local phone")
        with self.assertRaises(LuminalApiException) as context:
            self._client().card_holders.add(replace(profile, phone=""))
        self.assertEqual(200, context.exception.http_status)
        self.assertEqual(400, context.exception.api_code)

    def test_create_and_query_cardholder_from_sandbox(self) -> None:
        holder_id = self._ensure_cardholder_id()
        detail = self._client().card_holders.detail(holder_id)
        self.assertIsNotNone(detail)
        self.assertEqual("Sdk", detail.last_name)
        page = self._client().card_holders.page(
            CardHolderPageRequest(page_no=1, page_size=20, card_holder_id=holder_id)
        )
        self._assert_page(page)
        self.assertTrue(any(item.card_holder_id == holder_id for item in page.list))

    def test_modify_cardholder_from_sandbox(self) -> None:
        holder = self._client().card_holders.detail(self._ensure_cardholder_id())
        self.assertIsNotNone(holder)
        updated_address = f"SDK address updated {int(time.time() * 1000)}"
        modified = False
        try:
            self._client().card_holders.modify(
                self._modify_request(holder, address_line2=updated_address)
            )
            modified = True
            current = self._client().card_holders.detail(holder.card_holder_id)
            self.assertEqual(updated_address, current.address_line2)
        finally:
            if modified:
                self._client().card_holders.modify(
                    self._modify_request(holder, address_line2=holder.address_line2)
                )

    def test_modify_cardholder_rejects_blank_phone_from_sandbox(self) -> None:
        before = self._client().card_holders.detail(self._ensure_cardholder_id())
        self.assertIsNotNone(before)
        invalid_request = self._modify_request(
            before,
            address_line2=before.address_line2,
            phone="",
        )
        with self.assertRaises(LuminalApiException) as context:
            self._client().card_holders.modify(invalid_request)
        self.assertEqual(200, context.exception.http_status)
        self.assertEqual(400, context.exception.api_code)
        after = self._client().card_holders.detail(before.card_holder_id)
        self.assertEqual(before.country_id, after.country_id)
        self.assertEqual(before.area_code, after.area_code)
        self.assertEqual(before.phone, after.phone)
        self.assertEqual(before.address_line2, after.address_line2)

    def test_reuse_existing_cardholder_for_recharge_card_issue_from_sandbox(self) -> None:
        if self._supports_custom_cardholder():
            self.assertTrue(self._ensure_cardholder_id())

    def test_issue_recharge_card_from_sandbox(self) -> None:
        self.assertTrue(self._issue_task_id())

    def test_wait_for_recharge_card_open_from_sandbox(self) -> None:
        self.assertTrue(self._ensure_recharge_card_id())

    def test_list_recharge_cards_from_sandbox(self) -> None:
        card_id = self._ensure_recharge_card_id()
        page = self._client().cards.list(
            MemberCardPageRequest(
                page_no=1,
                page_size=20,
                member_card_id=card_id,
                card_type=CURRENT_CARD_TYPE,
                card_groups=[self._ensure_recharge_card_group().card_group_id],
            )
        )
        self._assert_page(page)
        self.assertTrue(any(item.member_card_id == card_id for item in page.list))

    def test_list_cards_associated_with_cardholder_from_sandbox(self) -> None:
        if not self._supports_custom_cardholder():
            self.skipTest("selected recharge-card BIN does not support explicit cardholders")
        card_id = self._ensure_recharge_card_id()
        page = self._client().card_holders.associated_cards(
            CardHolderCardPageRequest(
                page_no=1,
                page_size=20,
                card_holder_id=self._ensure_cardholder_id(),
                member_card_id=card_id,
            )
        )
        self._assert_page(page)
        self.assertTrue(any(item.member_card_id == card_id for item in page.list))

    def test_get_recharge_card_cvv_from_sandbox(self) -> None:
        result = self._client().cards.cvv(CardIdRequest(self._ensure_recharge_card_id()))
        self.assertIsNotNone(result)

    def test_get_recharge_card_limit_from_sandbox(self) -> None:
        result = self._client().cards.limit(CardIdRequest(self._ensure_recharge_card_id()))
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.balance)

    def test_modify_recharge_card_limit_from_sandbox(self) -> None:
        if not self._supports_card_limit():
            self.skipTest("selected recharge-card BIN does not support limit modification")
        global _CACHED_LIMIT_OPERATION_ID
        request = CardLimitUpdateRequest(
            member_card_id=self._ensure_recharge_card_id(),
            card_type=CURRENT_CARD_TYPE,
            daily_limit=_configured_decimal("LUMINAL_OPEN_API_RECHARGE_DAILY_LIMIT", None, "100.00"),
            month_limit=_configured_decimal("LUMINAL_OPEN_API_RECHARGE_MONTH_LIMIT", None, "1000.00"),
            total_limit=None,
        )
        _CACHED_LIMIT_OPERATION_ID = self._client().cards.modify_limit_async(request)
        self.assertTrue(_CACHED_LIMIT_OPERATION_ID)
        result = self._await_operation(_CACHED_LIMIT_OPERATION_ID, LIMIT_OPERATION_TYPE)
        self.assertEqual("SUCCESS", str(result.status).upper())

    def test_recharge_card_from_sandbox(self) -> None:
        global _CACHED_RECHARGE_OPERATION_ID
        request = MemberCardRechargeRequest(
            member_card_id=self._ensure_recharge_card_id(),
            amount=_configured_decimal("LUMINAL_OPEN_API_RECHARGE_AMOUNT", None, "10.00"),
            remark="python-sdk Sandbox recharge",
        )
        _CACHED_RECHARGE_OPERATION_ID = self._client().cards.recharge(request)
        self.assertTrue(_CACHED_RECHARGE_OPERATION_ID)
        result = self._await_operation(_CACHED_RECHARGE_OPERATION_ID, "RECHARGE")
        self.assertEqual("SUCCESS", str(result.status).upper())

    def test_query_recharge_operation_record_from_sandbox(self) -> None:
        self.assertTrue(_CACHED_RECHARGE_OPERATION_ID)
        result = self._client().cards.operation_record(
            RechargeCardOperationRecordRequest(_CACHED_RECHARGE_OPERATION_ID)
        )
        self.assertIsNotNone(result)
        self.assertEqual("RECHARGE", str(result.operation_type).upper())
        self.assertEqual("SUCCESS", str(result.status).upper())

    def test_withdraw_card_from_sandbox(self) -> None:
        global _CACHED_WITHDRAW_OPERATION_ID
        request = MemberCardWithdrawRequest(
            member_card_id=self._ensure_recharge_card_id(),
            amount=_configured_decimal("LUMINAL_OPEN_API_WITHDRAW_AMOUNT", None, "19.90"),
            remark="python-sdk Sandbox withdrawal",
        )
        _CACHED_WITHDRAW_OPERATION_ID = self._client().cards.withdraw(request)
        self.assertTrue(_CACHED_WITHDRAW_OPERATION_ID)
        result = self._await_operation(_CACHED_WITHDRAW_OPERATION_ID, "WITHDRAW")
        self.assertEqual("SUCCESS", str(result.status).upper())

    def test_query_withdraw_operation_record_from_sandbox(self) -> None:
        self.assertTrue(_CACHED_WITHDRAW_OPERATION_ID)
        result = self._client().cards.operation_record(
            RechargeCardOperationRecordRequest(_CACHED_WITHDRAW_OPERATION_ID)
        )
        self.assertIsNotNone(result)
        self.assertEqual("WITHDRAW", str(result.operation_type).upper())
        self.assertEqual("SUCCESS", str(result.status).upper())

    def test_list_recharge_card_transactions_from_sandbox(self) -> None:
        card_id = self._ensure_recharge_card_id()
        page = self._client().cards.transactions(
            CardTransactionsRequest(
                page_no=1,
                page_size=20,
                card_type=CURRENT_CARD_TYPE,
                member_card_id=card_id,
            )
        )
        self._assert_page(page)
        webhook = _TRANSACTION_WEBHOOKS.get(str(card_id))
        if webhook is not None:
            self.assertEqual(CURRENT_CARD_TYPE, str(webhook.card_type).upper())
            self.assertEqual(str(card_id), str(webhook.member_card_id))
        for item in page.list:
            transaction_id = item.member_card_transaction_id
            settlement = _SETTLEMENT_WEBHOOKS.get(str(transaction_id))
            if settlement is not None:
                self.assertEqual(CURRENT_CARD_TYPE, str(settlement.card_type).upper())

    def test_freeze_recharge_card_from_sandbox(self) -> None:
        card_id = self._ensure_recharge_card_id()
        self._clear_card_status(card_id)
        self.assertTrue(self._client().cards.freeze(CardIdRequest(card_id)))
        self._await_card_status(card_id, "FREEZE")

    def test_unfreeze_recharge_card_from_sandbox(self) -> None:
        card_id = self._ensure_recharge_card_id()
        self._clear_card_status(card_id)
        self.assertTrue(self._client().cards.unfreeze(CardIdRequest(card_id)))
        self._await_card_status(card_id, "ACTIVE")

    def test_cancel_recharge_card_from_sandbox(self) -> None:
        card_id = self._ensure_recharge_card_id()
        self._clear_card_status(card_id)
        self.assertTrue(self._client().cards.cancel(CardIdRequest(card_id)))
        self._await_card_status(card_id, "CANCEL")


_TEST_ORDER = (
    "test_get_token_from_sandbox",
    "test_list_recharge_card_bins_from_sandbox",
    "test_create_recharge_card_group_from_sandbox",
    "test_list_cardholder_countries_from_sandbox",
    "test_create_cardholder_rejects_blank_phone_from_sandbox",
    "test_create_and_query_cardholder_from_sandbox",
    "test_modify_cardholder_from_sandbox",
    "test_modify_cardholder_rejects_blank_phone_from_sandbox",
    "test_reuse_existing_cardholder_for_recharge_card_issue_from_sandbox",
    "test_issue_recharge_card_from_sandbox",
    "test_wait_for_recharge_card_open_from_sandbox",
    "test_list_recharge_cards_from_sandbox",
    "test_list_cards_associated_with_cardholder_from_sandbox",
    "test_get_recharge_card_cvv_from_sandbox",
    "test_get_recharge_card_limit_from_sandbox",
    "test_modify_recharge_card_limit_from_sandbox",
    "test_recharge_card_from_sandbox",
    "test_query_recharge_operation_record_from_sandbox",
    "test_withdraw_card_from_sandbox",
    "test_query_withdraw_operation_record_from_sandbox",
    "test_list_recharge_card_transactions_from_sandbox",
    "test_freeze_recharge_card_from_sandbox",
    "test_unfreeze_recharge_card_from_sandbox",
    "test_cancel_recharge_card_from_sandbox",
)


def load_tests(loader: Any, tests: Any, pattern: str | None) -> unittest.TestSuite:
    """Match the Java integration-test order instead of unittest name sorting."""

    return unittest.TestSuite(
        RechargeCardSandboxOpenApiIntegrationTest(test_name) for test_name in _TEST_ORDER
    )


if __name__ == "__main__":
    unittest.main()
