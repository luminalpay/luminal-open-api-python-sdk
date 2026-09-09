"""Standalone client for every enabled Luminal Open API controller endpoint."""

from __future__ import annotations

import base64
import threading
import time
from typing import Any, Callable, TypeVar

from .codec import decode_value
from .crypto import RsaPrivateKey, read_private_key, sign
from .models import (
    CardBinResponse,
    CardBinsRequest,
    CardCvvResponse,
    CardGroupCreateRequest,
    CardGroupDeleteRequest,
    CardGroupRequest,
    CardGroupResponse,
    CardGroupUpdateRequest,
    CardHolderCardPageRequest,
    CardHolderCardResponse,
    CardHolderCountryResponse,
    CardHolderCreateRequest,
    CardHolderDetailResponse,
    CardHolderModifyRequest,
    CardHolderPageRequest,
    CardHolderPageResponse,
    CardIdRequest,
    CardLimitResponse,
    CardLimitUpdateRequest,
    CardPoolRequest,
    CardPoolResponse,
    CardTransactionResponse,
    CardTransactionsRequest,
    CreateSharedAccountRequest,
    IssueCardDetailsRequest,
    IssueCardDetailsResponse,
    IssueCardRequest,
    Long,
    MemberCardPageRequest,
    MemberCardResponse,
    MemberCardRechargeRequest,
    MemberCardWithdrawRequest,
    OAuth2Token,
    PageResult,
    PageResultEx,
    RechargeCardOperationRecordRequest,
    RechargeCardOperationRecordResponse,
    RefreshTokenRequest,
    SharedAccountBalanceRequest,
    SharedAccountCancelRequest,
    SharedAccountGetRequest,
    SharedAccountIdResponse,
    SharedAccountPageRequest,
    SharedAccountResponse,
    SharedAccountTransactionIdResponse,
    SharedAccountTransactionResponse,
    SharedAccountTransactionsRequest,
    WalletInfoRequest,
    WalletInfoResponse,
    WalletTransactionRequest,
    WalletTransactionResponse,
)
from .webhooks import WebhookEvent, WebhookVerifier
from .transport import (
    _DEFAULT_MAX_RESPONSE_BYTES,
    HttpTransport,
    require_non_blank,
    serialize_json,
    serialize_json_for_signature,
)

T = TypeVar("T")


def _decode_model(model_type: type[T]) -> Callable[[Any], T | None]:
    return lambda value: decode_value(value, model_type)


def _decode_page(data: Any, item_type: type[T], extended: bool) -> PageResult[T] | PageResultEx[T]:
    if data is None:
        return None  # type: ignore[return-value]
    if not isinstance(data, dict):
        raise ValueError("Expected a paginated response object")
    items = data.get("list")
    if items is not None and not isinstance(items, list):
        raise ValueError("Expected paginated response list to be an array")
    decoded_items = None if items is None else [decode_value(item, item_type) for item in items]
    total = decode_value(data.get("total"), Long)
    if extended:
        return PageResultEx(total=total, list=decoded_items, extra=data.get("extra"))
    return PageResult(total=total, list=decoded_items)


def _decode_list(data: Any, item_type: type[T]) -> list[T] | None:
    if data is None:
        return None
    if not isinstance(data, list):
        raise ValueError("Expected a response array")
    return [decode_value(item, item_type) for item in data]


def _decode_bool(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError("Expected a JSON boolean")
    return value


def _require_request(request: Any) -> Any:
    if request is None:
        raise ValueError("request must not be None")
    return request

class _OAuthTokenCache:
    def __init__(self, client: "LuminalOpenApiClient", app_id: str, app_secret: str, refresh_ratio: float) -> None:
        self._client = client
        self._app_id = require_non_blank(app_id, "app_id")
        self._app_secret = require_non_blank(app_secret, "app_secret")
        if not isinstance(refresh_ratio, (int, float)) or not 0 < refresh_ratio <= 1:
            raise ValueError("token_refresh_ratio must be in (0, 1]")
        self._refresh_ratio = float(refresh_ratio)
        self._lock = threading.Lock()
        self._token: OAuth2Token | None = None
        self._acquired_at_ms: int | None = None

    def __call__(self, force_refresh: bool = False) -> str | None:
        token = self._token
        if not force_refresh and token is not None and not self._needs_refresh(token):
            return token.access_token
        with self._lock:
            token = self._token
            if not force_refresh and token is not None and not self._needs_refresh(token):
                return token.access_token
            token = self._client.auth.get_token(self._app_id, self._app_secret)
            self._token = token
            self._acquired_at_ms = int(time.time() * 1000)
            return token.access_token

    def _needs_refresh(self, token: OAuth2Token) -> bool:
        expires = token.expires_time
        if expires is None or self._acquired_at_ms is None:
            return True
        if expires < 1_000_000_000_000:
            expires *= 1000
        ttl = expires - self._acquired_at_ms
        if ttl <= 0:
            return True
        remaining = expires - int(time.time() * 1000)
        return remaining <= ttl * self._refresh_ratio



class AuthApi:
    """Authorization endpoints."""

    _PATH = "/open-api/v1/auth"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_token(self, app_id: str, app_secret: str) -> OAuth2Token | None:
        """Obtain an OAuth2 token using HTTP Basic authorization."""
        credentials = f"{require_non_blank(app_id, 'app_id')}:{require_non_blank(app_secret, 'app_secret')}"
        authorization = "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        return self._transport.post(
            self._PATH + "/token",
            headers={"Authorization": authorization},
            authorized=False,
            decoder=_decode_model(OAuth2Token),
        )

    def refresh_token(self, refresh_token: str) -> OAuth2Token | None:
        """Exchange a refresh token for a new OAuth2 token."""
        request = RefreshTokenRequest(require_non_blank(refresh_token, "refresh_token"))
        return self._transport.post(
            self._PATH + "/refresh-token",
            request,
            decoder=_decode_model(OAuth2Token),
        )

    def logout(self) -> bool:
        """Invalidate the configured bearer token."""
        return self._transport.post(self._PATH + "/logout", decoder=_decode_bool)


class AccountsApi:
    """Wallet-account endpoints."""

    _PATH = "/open-api/v1/accounts"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def list(self, request: WalletInfoRequest) -> PageResultEx[WalletInfoResponse] | None:
        """List wallet accounts for the current member."""
        return self._transport.post(
            self._PATH,
            _require_request(request),
            decoder=lambda data: _decode_page(data, WalletInfoResponse, True),
        )


class TransactionsApi:
    """Wallet-transaction endpoints."""

    _PATH = "/open-api/v1/transactions"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def list(self, request: WalletTransactionRequest) -> PageResult[WalletTransactionResponse] | None:
        """List wallet transactions for the current member."""
        return self._transport.post(
            self._PATH + "/list",
            _require_request(request),
            decoder=lambda data: _decode_page(data, WalletTransactionResponse, False),
        )


class SharedAccountsApi:
    """Shared-account endpoints."""

    _PATH = "/open-api/v1/shared-account"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def create(self, request: CreateSharedAccountRequest) -> SharedAccountIdResponse | None:
        """Create and initially fund a shared account."""
        return self._post("/create", request, SharedAccountIdResponse)

    def list(self, request: SharedAccountPageRequest) -> PageResultEx[SharedAccountResponse] | None:
        """List shared accounts for the current member."""
        return self._transport.post(
            self._PATH + "/list",
            _require_request(request),
            decoder=lambda data: _decode_page(data, SharedAccountResponse, True),
        )

    def increase(self, request: SharedAccountBalanceRequest) -> SharedAccountTransactionIdResponse | None:
        """Deposit funds into a shared account."""
        return self._post("/increase", request, SharedAccountTransactionIdResponse)

    def decrease(self, request: SharedAccountBalanceRequest) -> SharedAccountTransactionIdResponse | None:
        """Withdraw funds from a shared account."""
        return self._post("/decrease", request, SharedAccountTransactionIdResponse)

    def cancel(self, request: SharedAccountCancelRequest) -> bool:
        """Cancel a shared account with the server-required verification code."""
        return self._action("/cancel", request)

    def details(self, request: SharedAccountGetRequest) -> SharedAccountResponse | None:
        """Retrieve one shared account and its supported operations."""
        return self._post("/details", request, SharedAccountResponse)

    def transactions(self, request: SharedAccountTransactionsRequest) -> PageResultEx[SharedAccountTransactionResponse] | None:
        """List shared-account fund transactions."""
        return self._transport.post(
            self._PATH + "/transactions",
            _require_request(request),
            decoder=lambda data: _decode_page(data, SharedAccountTransactionResponse, True),
        )

    def _post(self, path: str, request: Any, model_type: type[T]) -> T | None:
        return self._transport.post(
            self._PATH + path,
            _require_request(request),
            decoder=_decode_model(model_type),
        )

    def _action(self, path: str, request: Any) -> bool:
        return self._transport.post(self._PATH + path, _require_request(request), decoder=_decode_bool)


class CardPoolsApi:
    """Card-pool endpoints."""

    _PATH = "/open-api/v1/cards/pools"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def list(self, request: CardPoolRequest) -> list[CardPoolResponse] | None:
        """List card pools available to the current member."""
        return self._transport.post(
            self._PATH,
            _require_request(request),
            decoder=lambda data: _decode_list(data, CardPoolResponse),
        )


class CardsApi:
    """Card endpoints, including signed card issuance."""

    _PATH = "/open-api/v1/cards"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def bins(self, request: CardBinsRequest) -> PageResultEx[CardBinResponse] | None:
        """List available card BIN products."""
        return self._page("/bins", request, CardBinResponse)

    def issue(self, request: IssueCardRequest, signature_or_private_key: str | RsaPrivateKey) -> Long | None:
        """Submit a signed card-issuance request.

        A non-PEM string is treated as a precomputed Base64 signature. An RSA private-key
        object or PEM string signs the API's canonical signature JSON.
        """
        if isinstance(signature_or_private_key, RsaPrivateKey):
            signature = self.sign_issue_request(request, signature_or_private_key)
        elif isinstance(signature_or_private_key, str) and "-----BEGIN" in signature_or_private_key:
            signature = self.sign_issue_request(request, read_private_key(signature_or_private_key))
        else:
            signature = require_non_blank(signature_or_private_key, "signature")
        body = serialize_json(_require_request(request))
        return self._transport.post_serialized(
            self._PATH + "/issue",
            body,
            headers={"sign": signature},
            decoder=lambda data: decode_value(data, Long),
        )

    def sign_issue_request(self, request: IssueCardRequest, private_key: RsaPrivateKey | str) -> str:
        """Sign canonical card-issuance JSON with an RSA private key."""
        key = read_private_key(private_key) if isinstance(private_key, str) else private_key
        if not isinstance(key, RsaPrivateKey):
            raise TypeError("private_key must be RsaPrivateKey or PEM text")
        return sign(serialize_json_for_signature(_require_request(request)), key)

    def list(self, request: MemberCardPageRequest) -> PageResultEx[MemberCardResponse] | None:
        """List issued cards for the current member."""
        return self._page("/list", request, MemberCardResponse)

    def cvv(self, request: CardIdRequest) -> CardCvvResponse | None:
        """Retrieve sensitive card number, CVV, and expiry data."""
        return self._post("/cvv", request, CardCvvResponse)

    def transactions(self, request: CardTransactionsRequest) -> PageResultEx[CardTransactionResponse] | None:
        """List card transactions."""
        return self._page("/transactions", request, CardTransactionResponse)

    def limit(self, request: CardIdRequest) -> CardLimitResponse | None:
        """Retrieve the current card limit and balance."""
        return self._post("/limit", request, CardLimitResponse)

    def modify_limit(self, request: CardLimitUpdateRequest) -> bool:
        """Update a card limit."""
        return self._action("/limit/modify", request)

    def modify_limit_async(self, request: CardLimitUpdateRequest) -> Long | None:
        """Update a card limit asynchronously and return its operation-record identifier."""
        return self._post("/limit/modify/operation-record", request, Long)

    def freeze(self, request: CardIdRequest) -> bool:
        """Freeze a card."""
        return self._action("/freeze", request)

    def unfreeze(self, request: CardIdRequest) -> bool:
        """Unfreeze a card."""
        return self._action("/unfreeze", request)

    def cancel(self, request: CardIdRequest) -> bool:
        """Cancel a card."""
        return self._action("/cancel", request)

    def recharge(self, request: MemberCardRechargeRequest) -> Long | None:
        """Submit a rechargeable-card funding request."""
        return self._post("/recharge", request, Long)

    def withdraw(self, request: MemberCardWithdrawRequest) -> Long | None:
        """Submit a rechargeable-card withdrawal request."""
        return self._post("/withdraw", request, Long)

    def operation_record(
        self, request: RechargeCardOperationRecordRequest
    ) -> RechargeCardOperationRecordResponse | None:
        """Return the first operation record matching the supplied query, if any."""
        page = self.operation_records(request)
        if page is None or not page.list:
            return None
        return page.list[0]

    def operation_records(
        self, request: RechargeCardOperationRecordRequest
    ) -> PageResultEx[RechargeCardOperationRecordResponse] | None:
        """Query rechargeable-card funding, withdrawal, and limit operations."""
        return self._page("/operation-record", request, RechargeCardOperationRecordResponse)

    def issue_details(self, request: IssueCardDetailsRequest) -> list[IssueCardDetailsResponse] | None:
        """Retrieve per-card results for an issuance task."""
        return self._transport.post(
            self._PATH + "/issue/detail",
            _require_request(request),
            decoder=lambda data: _decode_list(data, IssueCardDetailsResponse),
        )

    def _post(self, path: str, request: Any, model_type: type[T]) -> T | None:
        return self._transport.post(
            self._PATH + path,
            _require_request(request),
            decoder=_decode_model(model_type),
        )

    def _page(self, path: str, request: Any, model_type: type[T]) -> PageResultEx[T] | None:
        return self._transport.post(
            self._PATH + path,
            _require_request(request),
            decoder=lambda data: _decode_page(data, model_type, True),
        )

    def _action(self, path: str, request: Any) -> bool:
        return self._transport.post(self._PATH + path, _require_request(request), decoder=_decode_bool)


class CardHoldersApi:
    """Cardholder management endpoints."""

    _PATH = "/open-api/v1/card-holders"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def add(self, request: CardHolderCreateRequest) -> Long | None:
        """Create a cardholder and return its identifier."""
        return self._post("/add", request, Long)

    def countries(self) -> list[CardHolderCountryResponse] | None:
        """List countries and regions available for cardholder information."""
        return self._transport.get(
            self._PATH + "/countries",
            decoder=lambda data: _decode_list(data, CardHolderCountryResponse),
        )

    def modify(self, request: CardHolderModifyRequest) -> None:
        """Update all editable fields of a cardholder."""
        self._transport.post(
            self._PATH + "/modify",
            _require_request(request),
            decoder=lambda _data: None,
        )

    def detail(self, card_holder_id: Long) -> CardHolderDetailResponse | None:
        """Retrieve cardholder details by identifier."""
        if card_holder_id is None:
            raise ValueError("card_holder_id must not be None")
        return self._post(f"/info/{card_holder_id}", {}, CardHolderDetailResponse)

    def page(self, request: CardHolderPageRequest) -> PageResult[CardHolderPageResponse] | None:
        """List cardholders owned by the current member."""
        return self._transport.post(
            self._PATH + "/page",
            _require_request(request),
            decoder=lambda data: _decode_page(data, CardHolderPageResponse, False),
        )

    def associated_cards(
        self, request: CardHolderCardPageRequest
    ) -> PageResult[CardHolderCardResponse] | None:
        """List cards associated with a cardholder."""
        return self._transport.post(
            self._PATH + "/card/page",
            _require_request(request),
            decoder=lambda data: _decode_page(data, CardHolderCardResponse, False),
        )

    def _post(self, path: str, request: Any, model_type: type[T]) -> T | None:
        return self._transport.post(
            self._PATH + path,
            _require_request(request),
            decoder=_decode_model(model_type),
        )


class CardGroupsApi:
    """Card-group endpoints."""

    _PATH = "/open-api/v1/cards/group"

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def list(self, request: CardGroupRequest) -> PageResultEx[CardGroupResponse] | None:
        """List card groups for the current member."""
        return self._transport.post(
            self._PATH,
            _require_request(request),
            decoder=lambda data: _decode_page(data, CardGroupResponse, True),
        )

    def create(self, request: CardGroupCreateRequest) -> CardGroupResponse | None:
        """Create a card group."""
        return self._post("/create", request, CardGroupResponse)

    def update(self, request: CardGroupUpdateRequest) -> bool:
        """Update a card-group name."""
        return self._action("/update", request)

    def delete(self, request: CardGroupDeleteRequest) -> bool:
        """Delete a card group."""
        return self._action("/delete", request)

    def _post(self, path: str, request: Any, model_type: type[T]) -> T | None:
        return self._transport.post(
            self._PATH + path,
            _require_request(request),
            decoder=_decode_model(model_type),
        )

    def _action(self, path: str, request: Any) -> bool:
        return self._transport.post(self._PATH + path, _require_request(request), decoder=_decode_bool)


class LuminalOpenApiClient:
    """Standalone Python 3 client for all enabled Luminal Open API endpoints."""

    def __init__(
        self,
        base_url: str,
        bearer_token: str | None = None,
        *,
        timeout: float = 30.0,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
        opener: Callable[..., Any] | None = None,
        app_id: str | None = None,
        app_secret: str | None = None,
        token_refresh_ratio: float = 0.5,
        retry_unauthorized: int = 1,
        accept_language: str = "en",
        log_http: bool = True,
        log_raw_http: bool = False,
        logger: Any | None = None,
    ) -> None:
        self._token_cache: _OAuthTokenCache | None = None
        transport_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "max_response_bytes": max_response_bytes,
            "opener": opener,
            "accept_language": accept_language,
            "retry_unauthorized": retry_unauthorized,
            "log_http": log_http,
            "log_raw_http": log_raw_http,
            "logger": logger,
        }
        if app_id is not None or app_secret is not None:
            if app_id is None or app_secret is None:
                raise ValueError("app_id and app_secret must be provided together")
            self._bind_apis(HttpTransport(base_url, bearer_token, **transport_kwargs))
            self._token_cache = _OAuthTokenCache(self, app_id, app_secret, token_refresh_ratio)
            self._transport._bearer_token_provider = self._token_cache
            return
        self._bind_apis(HttpTransport(base_url, bearer_token, **transport_kwargs))

    def parse_webhook(
        self, event: str, event_id: str, raw_body: bytes | str, signature: str, public_key: Any,
    ) -> WebhookEvent:
        webhook = WebhookVerifier.parse(event, event_id, raw_body, signature, public_key)
        self._transport._log_webhook(event, event_id, raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body)
        return webhook

    def with_bearer_token(self, token: str) -> "LuminalOpenApiClient":
        """Return a client using a different bearer token."""
        client = object.__new__(LuminalOpenApiClient)
        client._token_cache = None
        client._bind_apis(self._transport.with_bearer_token(token))
        return client

    def _bind_apis(self, transport: HttpTransport) -> None:
        self._transport = transport
        self.auth = AuthApi(transport)
        self.accounts = AccountsApi(transport)
        self.transactions = TransactionsApi(transport)
        self.shared_accounts = SharedAccountsApi(transport)
        self.card_pools = CardPoolsApi(transport)
        self.cards = CardsApi(transport)
        self.card_holders = CardHoldersApi(transport)
        self.card_groups = CardGroupsApi(transport)

    @property
    def transport(self) -> HttpTransport:
        """Return the underlying transport for advanced testing or integration."""
        return self._transport


