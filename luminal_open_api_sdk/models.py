"""Typed request and response models for the Luminal Open API SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
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
class SharedAccountCancelRequest:
    """Parameters for cancelling a shared account."""

    member_shared_account_id: Long | None = None
    remark: str | None = None
    verify_code: str | None = None


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
    settle_status: str | None = None
    settle_time: datetime | None = None
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
class CardHolderCreateRequest:
    """Parameters for creating a cardholder."""

    last_name: str | None = None
    first_name: str | None = None
    birth_date: date | None = None
    mail: str | None = None
    phone: str | None = None
    area_code: str | None = None
    country_id: Long | None = None
    postal_code: str | None = None
    state: str | None = None
    city: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None


@dataclass(frozen=True, slots=True)
class CardHolderModifyRequest:
    """Parameters for updating all editable cardholder fields."""

    card_holder_id: Long | None = None
    last_name: str | None = None
    first_name: str | None = None
    birth_date: date | None = None
    mail: str | None = None
    phone: str | None = None
    area_code: str | None = None
    country_id: Long | None = None
    postal_code: str | None = None
    state: str | None = None
    city: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None


@dataclass(frozen=True, slots=True)
class CardHolderPageRequest:
    """Filters for the cardholder list endpoint."""

    page_no: int | None = None
    page_size: int | None = None
    card_holder_id: Long | None = None
    name: str | None = None
    phone: str | None = None
    mail: str | None = None
    create_time: list[Long] | None = None


@dataclass(frozen=True, slots=True)
class CardHolderCardPageRequest:
    """Filters for cards associated with a cardholder."""

    page_no: int | None = None
    page_size: int | None = None
    card_holder_id: Long | None = None
    member_card_id: Long | None = None


@dataclass(frozen=True, slots=True)
class CardHolderDetailResponse:
    """Complete cardholder profile returned by the detail endpoint."""

    card_holder_id: Long | None = None
    last_name: str | None = None
    first_name: str | None = None
    birth_date: date | None = None
    mail: str | None = None
    phone: str | None = None
    area_code: str | None = None
    country_id: Long | None = None
    postal_code: str | None = None
    state: str | None = None
    city: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    create_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class CardHolderPageResponse:
    """Cardholder list item."""

    create_time: datetime | None = None
    card_holder_id: Long | None = None
    full_name: str | None = None
    full_phone: str | None = None
    mail: str | None = None


@dataclass(frozen=True, slots=True)
class CardHolderCardResponse:
    """Card associated with a cardholder."""

    member_card_id: Long | None = None
    mask_card_no: str | None = None
    open_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class CardHolderCountryResponse:
    """Country or region available for cardholder creation and updates."""

    country_id: Long | None = None
    country_name: str | None = None
    country_code: str | None = None
    area_code: str | None = None
    phone_max_length: int | None = None


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
    custom_cardholder: int | None = None
    can_limit: int | None = None


@dataclass(frozen=True, slots=True, init=False)
class IssueCardRequest:
    """Parameters for a signed card-issuance request."""

    apply_count: int | None = None
    card_bin_id: Long | None = None
    card_group_id: Long | None = None
    card_name: str | None = None
    card_type: str | None = None
    member_shared_account_id: Long | None = None
    daily_limit: Decimal | None = None
    month_limit: Decimal | None = None
    recharge_amount: Decimal | None = None
    card_holder_id: Long | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create an issue request using either the current or legacy positional shape.

        The Java SDK added ``dailyLimit`` and ``cardHolderId`` in the middle and at the
        end of the record.  The eight-argument form used by earlier Python releases is
        accepted as well, so its seventh and eighth values remain ``month_limit`` and
        ``recharge_amount``.
        """

        names = (
            "apply_count",
            "card_bin_id",
            "card_group_id",
            "card_name",
            "card_type",
            "member_shared_account_id",
            "daily_limit",
            "month_limit",
            "recharge_amount",
            "card_holder_id",
        )
        if len(args) > len(names):
            raise TypeError(f"IssueCardRequest expected at most {len(names)} arguments")

        if len(args) == 8 and not kwargs:
            values = dict.fromkeys(names, None)
            values.update(
                {
                    "apply_count": args[0],
                    "card_bin_id": args[1],
                    "card_group_id": args[2],
                    "card_name": args[3],
                    "card_type": args[4],
                    "member_shared_account_id": args[5],
                    "month_limit": args[6],
                    "recharge_amount": args[7],
                }
            )
        else:
            values = {name: None for name in names}
            for name, value in zip(names, args):
                values[name] = value
            unknown = set(kwargs) - set(names)
            if unknown:
                unexpected = next(iter(sorted(unknown)))
                raise TypeError(f"IssueCardRequest got an unexpected keyword argument {unexpected!r}")
            for name, value in kwargs.items():
                if name in names[: len(args)]:
                    raise TypeError(f"IssueCardRequest got multiple values for argument {name!r}")
                values[name] = value

        for name in names:
            object.__setattr__(self, name, values[name])


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
    daily_limit: Decimal | None = None
    month_limit: Decimal | None = None
    can_limit: int | None = None
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

    member_card_transaction_id: Long | None = None
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
    settle_status: str | None = None
    settle_time: datetime | None = None
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


@dataclass(frozen=True, slots=True, init=False)
class CardLimitUpdateRequest:
    """Parameters for changing a card limit."""

    member_card_id: Long | None = None
    # Java keeps this legacy component for source compatibility but marks it @JsonIgnore.
    card_type: str | None = field(default=None, metadata={"wire_ignore": True})
    daily_limit: Decimal | None = None
    month_limit: Decimal | None = None
    total_limit: Decimal | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create a limit request using either the old or current Java constructor shape."""

        names = ("member_card_id", "card_type", "daily_limit", "month_limit", "total_limit")
        if len(args) > len(names):
            raise TypeError(f"CardLimitUpdateRequest expected at most {len(names)} arguments")

        if len(args) == 2 and not kwargs:
            # Previous Python API: (member_card_id, total_limit).
            values = dict.fromkeys(names, None)
            values["member_card_id"], values["total_limit"] = args
        elif len(args) == 4 and not kwargs:
            # Current Java overload: (memberCardId, dailyLimit, monthLimit, totalLimit).
            values = dict.fromkeys(names, None)
            values.update(
                {
                    "member_card_id": args[0],
                    "daily_limit": args[1],
                    "month_limit": args[2],
                    "total_limit": args[3],
                }
            )
        else:
            values = {name: None for name in names}
            for name, value in zip(names, args):
                values[name] = value
            unknown = set(kwargs) - set(names)
            if unknown:
                unexpected = next(iter(sorted(unknown)))
                raise TypeError(
                    f"CardLimitUpdateRequest got an unexpected keyword argument {unexpected!r}"
                )
            for name, value in kwargs.items():
                if name in names[: len(args)]:
                    raise TypeError(f"CardLimitUpdateRequest got multiple values for argument {name!r}")
                values[name] = value

        for name in names:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True)
class MemberCardRechargeRequest:
    """Parameters for funding a rechargeable card."""

    member_card_id: Long | None = None
    amount: Decimal | None = None
    remark: str | None = None


@dataclass(frozen=True, slots=True)
class MemberCardWithdrawRequest:
    """Parameters for withdrawing funds from a rechargeable card."""

    member_card_id: Long | None = None
    amount: Decimal | None = None
    remark: str | None = None


@dataclass(frozen=True, slots=True, init=False)
class RechargeCardOperationRecordRequest:
    """Filters for rechargeable-card operation records."""

    page_no: int | None = 1
    page_size: int | None = 10
    member_card_operation_record_id: Long | None = None
    member_card_id: Long | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Support the Java convenience form ``(operation_record_id)`` and full fields."""

        names = (
            "page_no",
            "page_size",
            "member_card_operation_record_id",
            "member_card_id",
        )
        if len(args) == 1 and not kwargs:
            values = {"page_no": 1, "page_size": 10, "member_card_operation_record_id": args[0], "member_card_id": None}
        else:
            if len(args) > len(names):
                raise TypeError(f"RechargeCardOperationRecordRequest expected at most {len(names)} arguments")
            values = {"page_no": 1, "page_size": 10, "member_card_operation_record_id": None, "member_card_id": None}
            for name, value in zip(names, args):
                values[name] = value
            unknown = set(kwargs) - set(names)
            if unknown:
                unexpected = next(iter(sorted(unknown)))
                raise TypeError(
                    f"RechargeCardOperationRecordRequest got an unexpected keyword argument {unexpected!r}"
                )
            for name, value in kwargs.items():
                if name in names[: len(args)]:
                    raise TypeError(
                        f"RechargeCardOperationRecordRequest got multiple values for argument {name!r}"
                    )
                values[name] = value

        if values["member_card_operation_record_id"] is None and values["member_card_id"] is None:
            raise ValueError(
                "member_card_operation_record_id and member_card_id cannot both be None"
            )
        for name in names:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True)
class RechargeCardOperationRecordResponse:
    """Result of a rechargeable-card funding, withdrawal, or limit operation."""

    member_card_operation_record_id: Long | None = None
    member_card_id: Long | None = None
    card_type: str | None = None
    operation_type: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    balance: Decimal | None = None
    status: str | None = None
    message: str | None = None
    create_time: Long | None = None
    update_time: Long | None = None


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
class RechargeCardTransferStatusWebhook:
    """Payload for rechargeable-card funding, withdrawal, or limit webhooks."""

    member_card_operation_record_id: Long | None = None
    member_card_id: Long | None = None
    card_type: str | None = None
    operation_type: str | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    balance: Decimal | None = None
    status: str | None = None
    message: str | None = None
    update_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class TransactionWebhook:
    """Payload shared by transaction webhook events."""

    member_card_transaction_id: str | None = None
    card_type: str | None = None
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
    settle_status: str | None = None
    settle_time: datetime | None = None
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



