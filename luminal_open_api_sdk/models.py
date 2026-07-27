"""Typed request and response models for the Luminal Open API SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

T = TypeVar("T")
Long = Annotated[int, "java-long"]


@dataclass(frozen=True, slots=True)
class PageResult(Generic[T]):
    """A paginated response containing records and the total match count."""

    total: Long | None = None
    list: list[T] | None = None


@dataclass(frozen=True, slots=True)
class PageResultEx(Generic[T]):
    """A paginated response with endpoint-specific metadata."""

    total: Long | None = None
    list: list[T] | None = None
    extra: Any = None


@dataclass(frozen=True, slots=True)
class WalletInfoRequest:
    """Filters for the wallet-account list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class WalletInfoResponse:
    """Wallet-account information returned by the API."""

    balance: Decimal | None = None
    currency: str | None = None
    frozen_balance: Decimal | None = None
    member_no: str | None = None
    wallet_no: str | None = None
    wallet_status: str | None = None


@dataclass(frozen=True, slots=True)
class OAuth2Token:
    """OAuth2 access and refresh token data."""

    access_token: str | None = None
    token_type: str | None = None
    expires_time: Long | None = None
    refresh_token: str | None = None
    scope: str | None = None
    jti: str | None = None

    def __repr__(self) -> str:
        return (
            "OAuth2Token(access_token='<redacted>', token_type=%r, expires_time=%r, "
            "refresh_token='<redacted>', scope=%r, jti=%r)"
            % (self.token_type, self.expires_time, self.scope, self.jti)
        )


@dataclass(frozen=True, slots=True)
class RefreshTokenRequest:
    """Request body for refreshing an OAuth2 token."""

    refresh_token: str

    def __repr__(self) -> str:
        return "RefreshTokenRequest(refresh_token='<redacted>')"


@dataclass(frozen=True, slots=True)
class WalletTransactionRequest:
    """Filters for the wallet-transaction list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    type: int | None = None
    create_time: list[datetime] | None = None
    member_card_id: Long | None = None


@dataclass(frozen=True, slots=True)
class WalletTransactionResponse:
    """Wallet-transaction data returned by the API."""

    transaction_no: Long | None = None
    member_no: Long | None = None
    wallet_no: Long | None = None
    order_no: str | None = None
    type: int | None = None
    direction: int | None = None
    amount: Decimal | None = None
    fee: Decimal | None = None
    currency: str | None = None
    before_balance: Decimal | None = None
    after_balance: Decimal | None = None
    status: int | None = None
    remark: str | None = None
    create_time: datetime | None = None
    member_card_id: Long | None = None
    card_number: str | None = None


@dataclass(frozen=True, slots=True)
class CreateSharedAccountRequest:
    """Parameters for creating and initially funding a shared account."""

    card_bin_id: Long | None = None
    recharge_amount: Decimal | None = None
    account_name: str | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountIdResponse:
    """Identifier returned after creating a shared account."""

    member_shared_account_id: Long | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountPageRequest:
    """Filters for the shared-account list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    member_shared_account_id: Long | None = None
    account_name: str | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountResponse:
    """Shared-account details and server-provided operation flags."""

    member_shared_account_id: Long | None = None
    account_name: str | None = None
    status: str | None = None
    create_time: datetime | None = None
    card_bin: str | None = None
    card_bin_id: Long | None = None
    card_organization: str | None = None
    balance: Decimal | None = None
    issued_card_count: Long | None = None
    remaining_apply_card_count: Long | None = None
    can_recharge: int | None = None
    can_apply: int | None = None
    apply_handling_fee: Decimal | None = None
    can_reduce: int | None = None
    can_freeze: int | None = None
    can_unfreeze: int | None = None
    can_cancel: int | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountBalanceRequest:
    """Parameters for depositing to or withdrawing from a shared account."""

    member_shared_account_id: Long | None = None
    amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountTransactionIdResponse:
    """Identifier returned after submitting a shared-account transaction."""

    shared_account_transaction_id: str | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountGetRequest:
    """Parameters for retrieving one shared account."""

    member_shared_account_id: Long | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountTransactionsRequest:
    """Filters for the shared-account transaction list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    shared_account_transaction_id: Long | None = None
    member_shared_account_id: Long | None = None
    member_card_id: Long | None = None
    type: str | None = None
    trade_time: list[datetime] | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountTransactionResponse:
    """Shared-account transaction data returned by the API."""

    shared_account_transaction_id: Long | None = None
    member_shared_account_id: Long | None = None
    member_card_id: Long | None = None
    mask_card_no: str | None = None
    order_no: str | None = None
    original_order_no: str | None = None
    account_balance: Decimal | None = None
    balance: Decimal | None = None
    before_balance: Decimal | None = None
    before_account_balance: Decimal | None = None
    status: str | None = None
    type: str | None = None
    trade_type: str | None = None
    description: str | None = None
    trade_actual_amount: Decimal | None = None
    currency_code: str | None = None
    trade_currency_code: str | None = None
    trade_amount: Decimal | None = None
    trade_time: datetime | None = None
    merchant_name: str | None = None
    merchant_id: str | None = None
    merchant_country: str | None = None
    card_bin: str | None = None
    merchant_city: str | None = None
    merchant_mcc: str | None = None
    process_status: str | None = None


@dataclass(frozen=True, slots=True)
class CardBinsRequest:
    """Filters for available card BIN products."""

    page_no: int | None = None
    page_size: int | None = None
    card_type: str | None = None
    card_organization: str | None = None
    card_bin: str | None = None
    area_code: str | None = None


@dataclass(frozen=True, slots=True)
class CardBinResponse:
    """Card BIN product information."""

    card_bin_id: Long | None = None
    card_type: str | None = None
    currency_code: str | None = None
    area_code: str | None = None
    card_bin: str | None = None
    card_organization: str | None = None
    applicable_scenarios: str | None = None


@dataclass(frozen=True, slots=True)
class IssueCardRequest:
    """Parameters for a signed card-issuance request."""

    apply_count: int | None = None
    card_bin_id: Long | None = None
    card_group_id: Long | None = None
    card_name: str | None = None
    card_type: str | None = None
    member_shared_account_id: Long | None = None
    month_limit: Decimal | None = None
    recharge_amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class MemberCardPageRequest:
    """Filters for the issued-card list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    member_card_id: Long | None = None
    status: str | None = None
    card_bin: str | None = None
    card_type: str | None = None
    card_key_words: str | None = None
    card_groups: list[Long] | None = None


@dataclass(frozen=True, slots=True)
class MemberCardResponse:
    """Issued-card information returned by the API."""

    member_card_id: Long | None = None
    member_shared_account_id: Long | None = None
    card_bin_id: Long | None = None
    card_bin: str | None = None
    card_type: str | None = None
    card_no: str | None = None
    card_tail_no: str | None = None
    currency_code: str | None = None
    balance: Decimal | None = None
    total_limit: Decimal | None = None
    status: str | None = None
    cardholder: str | None = None
    freeze_time: datetime | None = None
    cancel_time: datetime | None = None
    remark: str | None = None
    card_group_id: Long | None = None
    card_group_name: str | None = None
    # Java contract: Unix epoch milliseconds, not an ISO-8601 datetime.
    create_time: Long | None = None


@dataclass(frozen=True, slots=True)
class CardIdRequest:
    """Request containing one member-card identifier."""

    member_card_id: Long | None = None


@dataclass(frozen=True, slots=True)
class CardCvvResponse:
    """Sensitive card number, CVV, and expiry data."""

    member_card_id: Long | None = None
    card_no: str | None = None
    cvv: str | None = None
    expiry_date: str | None = None

    def __repr__(self) -> str:
        return (
            "CardCvvResponse(member_card_id=%r, card_no='<redacted>', "
            "cvv='<redacted>', expiry_date='<redacted>')" % self.member_card_id
        )


@dataclass(frozen=True, slots=True)
class CardTransactionsRequest:
    """Filters for the card-transaction list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    card_type: str | None = None
    member_card_id: Long | None = None
    trade_time: list[Long] | None = None


@dataclass(frozen=True, slots=True)
class CardTransactionResponse:
    """Card transaction data returned by the API."""

    shared_account_transaction_id: Long | None = None
    member_shared_account_id: Long | None = None
    member_card_id: Long | None = None
    mask_card_no: str | None = None
    order_no: str | None = None
    original_order_no: str | None = None
    account_balance: Decimal | None = None
    balance: Decimal | None = None
    before_balance: Decimal | None = None
    before_account_balance: Decimal | None = None
    status: str | None = None
    type: str | None = None
    trade_type: str | None = None
    direction: int | None = None
    description: str | None = None
    trade_actual_amount: Decimal | None = None
    currency_code: str | None = None
    trade_currency_code: str | None = None
    trade_amount: Decimal | None = None
    trade_time: datetime | None = None
    merchant_name: str | None = None
    merchant_id: str | None = None
    merchant_country: str | None = None
    card_bin: str | None = None
    merchant_city: str | None = None
    merchant_mcc: str | None = None
    process_status: str | None = None


@dataclass(frozen=True, slots=True)
class CardLimitResponse:
    """Current card limit and available balance."""

    member_card_id: Long | None = None
    total_limit: Decimal | None = None
    balance: Decimal | None = None


@dataclass(frozen=True, slots=True)
class CardLimitUpdateRequest:
    """Parameters for changing a card limit."""

    member_card_id: Long | None = None
    total_limit: Decimal | None = None


@dataclass(frozen=True, slots=True)
class IssueCardDetailsRequest:
    """Parameters for retrieving card-issuance task results."""

    task_id: Long | None = None


@dataclass(frozen=True, slots=True)
class IssueCardDetailsResponse:
    """Result for one card in an issuance task."""

    member_card_id: Long | None = None
    card_status: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class CardGroupRequest:
    """Filters for the card-group list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    card_type: str | None = None


@dataclass(frozen=True, slots=True)
class CardGroupResponse:
    """Card-group information returned by the API."""

    card_group_id: Long | None = None
    card_group_name: str | None = None
    card_type: str | None = None
    create_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class CardGroupCreateRequest:
    """Parameters for creating a card group."""

    card_group_name: str | None = None
    card_type: str | None = None


@dataclass(frozen=True, slots=True)
class CardGroupUpdateRequest:
    """Parameters for renaming a card group."""

    card_group_id: Long | None = None
    card_group_name: str | None = None


@dataclass(frozen=True, slots=True)
class CardGroupDeleteRequest:
    """Parameters for deleting a card group."""

    card_group_id: Long | None = None


@dataclass(frozen=True, slots=True)
class CardOpenResult:
    """One card result inside a card-opening webhook."""

    member_card_id: Long | None = None
    card_status: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class CardOpenStatusWebhook:
    """Payload for the CARD_OPEN_STATUS webhook event."""

    card_apply_task_id: Long | None = None
    member_id: Long | None = None
    list: list[CardOpenResult] | None = None


@dataclass(frozen=True, slots=True)
class CardStatusWebhook:
    """Payload for the CARD_STATUS webhook event."""

    member_card_id: str | None = None
    card_status: str | None = None
    member_no: str | None = None
    update_time: str | None = None


@dataclass(frozen=True, slots=True)
class SharedAccountOpenStatusWebhook:
    """Payload for the SHARED_ACCOUNT_OPEN_STATUS webhook event."""

    shared_account_operation_record_id: Long | None = None
    member_no: Long | None = None
    member_shared_account_id: Long | None = None
    status: str | None = None


@dataclass(frozen=True, slots=True)
class TransactionWebhook:
    """Payload shared by transaction webhook events."""

    shared_account_transaction_id: str | None = None
    member_shared_account_id: str | None = None
    member_card_id: str | None = None
    mask_card_no: str | None = None
    order_no: str | None = None
    original_order_no: str | None = None
    account_balance: Decimal | None = None
    balance: Decimal | None = None
    before_balance: Decimal | None = None
    before_account_balance: Decimal | None = None
    status: str | None = None
    type: str | None = None
    trade_type: str | None = None
    direction: str | None = None
    description: str | None = None
    trade_actual_amount: Decimal | None = None
    currency_code: str | None = None
    trade_currency_code: str | None = None
    trade_amount: Decimal | None = None
    trade_time: datetime | None = None
    merchant_name: str | None = None
    merchant_id: str | None = None
    merchant_country: str | None = None
    card_bin: str | None = None
    merchant_city: str | None = None
    merchant_mcc: str | None = None
    process_status: str | None = None



