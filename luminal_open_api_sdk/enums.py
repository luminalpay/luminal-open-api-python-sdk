from enum import Enum, IntEnum


class OpenApiScope(str, Enum):
    """OAuth2 permission scopes supported by the Open API."""

    ACCOUNT_READ = "openapi:account:read"
    CARD_READ = "openapi:card:read"
    CARD_ISSUE = "openapi:card:issue"
    CARD_FREEZE = "openapi:card:freeze"
    CARD_CANCEL = "openapi:card:cancel"
    CARD_LIMIT_WRITE = "openapi:card:limit:write"
    CARD_DETAIL_READ = "openapi:card:detail:read"
    CARD_GROUP_READ = "openapi:card-group:read"
    CARD_GROUP_WRITE = "openapi:card-group:write"
    RECHARGE_CARD_ISSUE = "openapi:recharge-card:issue"
    RECHARGE_CARD_RECHARGE = "openapi:recharge-card:recharge"
    RECHARGE_CARD_WITHDRAW = "openapi:recharge-card:withdraw"
    SHARED_ACCOUNT_READ = "openapi:shared-account:read"
    SHARED_ACCOUNT_CREATE = "openapi:shared-account:create"
    SHARED_ACCOUNT_DEPOSIT = "openapi:shared-account:deposit"
    SHARED_ACCOUNT_WITHDRAW = "openapi:shared-account:withdraw"
    SHARED_ACCOUNT_CANCEL = "openapi:shared-account:cancel"

    def code(self) -> str:
        """Return the scope value used on the wire."""

        return self.value


class CurrencyCode(str, Enum): USD = "USD"; HKD = "HKD"; EUR = "EUR"
class WalletStatus(str, Enum): ACTIVE = "ACTIVE"; DISABLED = "DISABLED"
class CardType(str, Enum): RECHARGE = "RECHARGE"; SHARED = "SHARED"
class CardStatus(str, Enum):
    UNACTIVE = "UNACTIVE"; APPLYING = "APPLYING"; ACTIVE = "ACTIVE"; FREEZE = "FREEZE"; PRE_FREEZE = "PRE_FREEZE"; PRE_UNFREEZE = "PRE_UNFREEZE"; RISK_FREEZE = "RISK_FREEZE"; ADMIN_FREEZE = "ADMIN_FREEZE"; PRE_CANCEL = "PRE_CANCEL"; CANCEL = "CANCEL"; RISK_CANCEL = "RISK_CANCEL"; ADMIN_CANCEL = "ADMIN_CANCEL"; EXPIRED = "EXPIRED"
class CardOrganization(str, Enum): VISA = "VISA"; MASTER_CARD = "MASTER_CARD"; DINNERS = "DINNERS"; AMEX = "AMEX"; JCB = "JCB"; DISCOVER = "DISCOVER"
class SharedAccountStatus(str, Enum):
    APPLYING = "APPLYING"; ACTIVE = "ACTIVE"; FREEZE = "FREEZE"; PRE_FREEZE = "PRE_FREEZE"; PRE_UNFREEZE = "PRE_UNFREEZE"; RISK_FREEZE = "RISK_FREEZE"; ADMIN_FREEZE = "ADMIN_FREEZE"; PRE_CANCEL = "PRE_CANCEL"; CANCEL = "CANCEL"; RISK_CANCEL = "RISK_CANCEL"; ADMIN_CANCEL = "ADMIN_CANCEL"
class AvailabilityFlag(IntEnum): NO = 0; YES = 1
class SharedAccountTransactionType(IntEnum): DEPOSIT = 101; WITHDRAW = 102; SHARED_ACCOUNT_ADJUST = 103; CARD_TRANSACTION = 1
class TradeStatus(str, Enum): SUCCESS = "SUCCESS"; FAIL = "FAIL"; PROCESSING = "PROCESSING"; PENDING = "PENDING"; REFUND_PENDING = "REFUND_PENDING"; REFUND = "REFUND"
class SettleStatus(str, Enum): SETTLED = "SETTLED"; PROCESSING = "PROCESSING"; PENDING = "PENDING"; NOT_SETTLE = "NOT_SETTLE"
class MemberTradeType(str, Enum): AUTH = "AUTH"; AUTH_VERIFY = "AUTH_VERIFY"; AUTH_REVOKE = "AUTH_REVOKE"; AUTH_REFUND = "AUTH_REFUND"; AUTH_CORRECTIVE = "AUTH_CORRECTIVE"; AUTH_REFUND_REVERSAL = "AUTH_REFUND_REVERSAL"; DISPUTED_REFUSAL = "DISPUTED_REFUSAL"
class TransactionDirection(IntEnum): TRANSFER_IN = 1; TRANSFER_OUT = 2
class ProcessStatus(str, Enum): PENDING = "PENDING"; PROCESSING = "PROCESSING"; SUCCESS = "SUCCESS"; FAIL = "FAIL"
class RechargeCardOperationType(str, Enum): RECHARGE = "RECHARGE"; WITHDRAW = "WITHDRAW"; MODIFY_LIMITS = "MODIFY_LIMITS"
class RechargeCardOperationStatus(str, Enum): PENDING = "PENDING"; PROCESSING = "PROCESSING"; SUCCESS = "SUCCESS"; FAIL = "FAIL"
class SharedAccountOpenStatus(str, Enum): SUCCESS = "SUCCESS"; FAIL = "FAIL"; PROCESSING = "PROCESSING"
class WalletTransactionType(IntEnum):
    DEPOSIT = 101; WITHDRAW = 102; WALLET_ADJUST = 103; FREEZE = 201; UNFREEZE = 202; APPLY_CARD_FEE = 1; CARD_RECHARGE = 2; CARD_RECHARGE_FEE = 3; CARD_REVOKE_FEE = 4; CARD_MIN_AMOUNT_FEE = 5; CARD_AUTH_FEE = 6; CARD_CROSS_BORDER_FEE = 7; CARD_OUT = 8; REFUND = 9; CARD_OUT_FEE = 10; TRANSFER_IN = 11; TRANSFER_OUT = 12; APPLY_ACCOUNT_FEE = 13; ACCOUNT_SERVICE_FEE = 14; SHARED_ACCOUNT_RECHARGE = 15; SHARED_ACCOUNT_REDUCE = 16; CARD_REFUND_FEE = 17
class WalletTransactionDirection(IntEnum): TRANSFER_INTO = 1; TRANSFER_OUT = 2
class WalletTransactionStatus(IntEnum): PROCESS = 0; SUCCESS = 1; FAIL = 2
