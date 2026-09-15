"""Independent webhook tests for every supported event type."""

from __future__ import annotations

import unittest
from decimal import Decimal

from luminal_open_api_sdk import (
    CardOpenStatusWebhook,
    CardStatusWebhook,
    RechargeCardTransferStatusWebhook,
    SharedAccountOpenStatusWebhook,
    TransactionWebhook,
    WebhookEventType,
    WebhookReplayGuard,
    WebhookVerificationException,
    WebhookVerifier,
    WalletTransactionWebhook,
    read_private_key,
    read_public_key,
    sign,
)

from tests.support import PRIVATE_KEY_PEM, PUBLIC_KEY_PEM, SANDBOX_WEBHOOK_PUBLIC_KEY_PEM



class SandboxWebhookPublicKeyTest(unittest.TestCase):
    def test_loads_sandbox_webhook_public_key(self) -> None:
        public_key = read_public_key(SANDBOX_WEBHOOK_PUBLIC_KEY_PEM)
        self.assertEqual(2048, public_key.modulus.bit_length())
        self.assertEqual(65537, public_key.public_exponent)


class CardTransactionsWebhookTest(unittest.TestCase):
    def test_verifies_and_decodes_transaction_payload(self) -> None:
        body = b'{ "memberCardId":"5", "tradeAmount": 10.50 }\n'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        event = WebhookVerifier.parse("CARD_TRANSACTIONS", "evt-1", body, signature, PUBLIC_KEY_PEM)
        self.assertEqual(WebhookEventType.CARD_TRANSACTIONS, event.type)
        self.assertIsInstance(event.payload, TransactionWebhook)
        self.assertEqual("5", event.payload.member_card_id)
        self.assertEqual(body, event.raw_body)


class CardStatusWebhookTest(unittest.TestCase):
    def test_verifies_and_decodes_card_status_payload(self) -> None:
        body = b'{"memberCardId":"5","cardStatus":"ACTIVE","memberNo":"M1","updateTime":"2026-07-20 10:00:00"}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        event = WebhookVerifier.parse(WebhookEventType.CARD_STATUS, "evt-2", body, signature, PUBLIC_KEY_PEM)
        self.assertIsInstance(event.payload, CardStatusWebhook)
        self.assertEqual("ACTIVE", event.payload.card_status)


class WalletTransactionsWebhookTest(unittest.TestCase):
    def test_verifies_and_decodes_wallet_transaction_payload(self) -> None:
        body = (
            b'{"transactionNo":10001,"memberNo":9,"walletNo":11,'
            b'"orderNo":"ORD-20260701-01","type":101,"direction":1,'
            b'"amount":12.34,"fee":0.12,"currency":"USD",'
            b'"beforeBalance":100,"afterBalance":112.22,"status":1,'
            b'"remark":"deposit","createTime":"2026-07-01T10:15:30",'
            b'"memberCardId":5,"cardNumber":"****1234"}'
        )
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))

        event = WebhookVerifier.parse(
            WebhookEventType.WALLET_TRANSACTIONS,
            "evt-wallet-1",
            body,
            signature,
            PUBLIC_KEY_PEM,
        )

        self.assertEqual(WebhookEventType.WALLET_TRANSACTIONS, event.type)
        self.assertIsInstance(event.payload, WalletTransactionWebhook)
        self.assertEqual(10001, event.payload.transaction_no)
        self.assertEqual(9, event.payload.member_no)
        self.assertEqual(11, event.payload.wallet_no)
        self.assertEqual("ORD-20260701-01", event.payload.order_no)
        self.assertEqual(101, event.payload.type)
        self.assertEqual(1, event.payload.direction)
        self.assertEqual(Decimal("12.34"), event.payload.amount)
        self.assertEqual(Decimal("0.12"), event.payload.fee)
        self.assertEqual("USD", event.payload.currency)
        self.assertEqual(Decimal("100"), event.payload.before_balance)
        self.assertEqual(Decimal("112.22"), event.payload.after_balance)
        self.assertEqual(1, event.payload.status)
        self.assertEqual("deposit", event.payload.remark)
        self.assertEqual("2026-07-01T10:15:30", event.payload.create_time.isoformat())
        self.assertEqual(5, event.payload.member_card_id)
        self.assertEqual("****1234", event.payload.card_number)


class RechargeCardLimitWebhookTest(unittest.TestCase):
    def test_decodes_recharge_card_limit_fields(self) -> None:
        body = (
            b'{"memberCardOperationRecordId":603,"memberCardId":5,'
            b'"cardType":"RECHARGE","operationType":"MODIFY_LIMITS",'
            b'"totalLimit":100,"dailyLimit":50,"monthLimit":500,'
            b'"status":"SUCCESS","message":"limit updated",'
            b'"updateTime":"2026-09-01T10:15:30"}'
        )
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))

        event = WebhookVerifier.parse(
            WebhookEventType.CARD_LIMIT_STATUS,
            "evt-limit-1",
            body,
            signature,
            PUBLIC_KEY_PEM,
        )

        self.assertIsInstance(event.payload, RechargeCardTransferStatusWebhook)
        self.assertEqual(603, event.payload.member_card_operation_record_id)
        self.assertEqual("MODIFY_LIMITS", event.payload.operation_type)
        self.assertEqual(Decimal("100"), event.payload.total_limit)
        self.assertEqual(Decimal("50"), event.payload.daily_limit)
        self.assertEqual(Decimal("500"), event.payload.month_limit)
        self.assertEqual("SUCCESS", event.payload.status)


class CardOpenStatusWebhookTest(unittest.TestCase):
    def test_verifies_and_decodes_card_open_status_payload(self) -> None:
        body = b'{"cardApplyTaskId":9,"memberId":8,"list":[{"memberCardId":7,"cardStatus":"ACTIVE"}]}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        event = WebhookVerifier.parse("CARD_OPEN_STATUS", "evt-3", body, signature, PUBLIC_KEY_PEM)
        self.assertIsInstance(event.payload, CardOpenStatusWebhook)
        self.assertEqual(7, event.payload.list[0].member_card_id)


class SharedAccountOpenStatusWebhookTest(unittest.TestCase):
    def test_verifies_and_decodes_shared_account_status_payload(self) -> None:
        body = b'{"sharedAccountOperationRecordId":1,"memberNo":2,"memberSharedAccountId":3,"status":"OPEN"}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        event = WebhookVerifier.parse(
            "SHARED_ACCOUNT_OPEN_STATUS", "evt-4", body, signature, PUBLIC_KEY_PEM
        )
        self.assertIsInstance(event.payload, SharedAccountOpenStatusWebhook)
        self.assertEqual(3, event.payload.member_shared_account_id)
        self.assertEqual("OPEN", event.payload.status)


class SharedAccountFundTransactionsWebhookTest(unittest.TestCase):
    def test_verifies_and_decodes_fund_transaction_payload(self) -> None:
        body = b'{"sharedAccountTransactionId":"tx-1","direction":"IN","tradeTime":"2026-07-20T10:00:00"}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        event = WebhookVerifier.parse(
            "SHARE_ACCOUNT_FUND_TRANSACTIONS", "evt-5", body, signature, PUBLIC_KEY_PEM
        )
        self.assertIsInstance(event.payload, TransactionWebhook)
        self.assertEqual("tx-1", event.payload.shared_account_transaction_id)
        self.assertEqual("IN", event.payload.direction)


class WebhookExactBytesTest(unittest.TestCase):
    def test_changed_whitespace_invalidates_signature(self) -> None:
        body = b'{"cardStatus":"ACTIVE"}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        self.assertTrue(WebhookVerifier.verify(body, signature, PUBLIC_KEY_PEM))
        self.assertFalse(WebhookVerifier.verify(b'{ "cardStatus":"ACTIVE" }', signature, PUBLIC_KEY_PEM))

    def test_invalid_signature_does_not_consume_event_id(self) -> None:
        guard = WebhookReplayGuard()
        with self.assertRaises(WebhookVerificationException):
            WebhookVerifier.parse("CARD_STATUS", "evt", b"{}", "bad", PUBLIC_KEY_PEM, replay_guard=guard)
        self.assertTrue(guard.accept("evt"))

    def test_replay_guard_rejects_duplicate_event_id(self) -> None:
        body = b'{"memberCardId":"5","cardStatus":"ACTIVE","memberNo":"M1","updateTime":"2026-07-20 10:00:00"}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        guard = WebhookReplayGuard()

        WebhookVerifier.parse(
            "CARD_STATUS", "evt-duplicate", body, signature, PUBLIC_KEY_PEM, replay_guard=guard
        )
        with self.assertRaisesRegex(WebhookVerificationException, "already been processed"):
            WebhookVerifier.parse(
                "CARD_STATUS", "evt-duplicate", body, signature, PUBLIC_KEY_PEM, replay_guard=guard
            )

    def test_replay_guard_rejects_invalid_configuration(self) -> None:
        for kwargs in (
            {"ttl_seconds": 0},
            {"ttl_seconds": float("inf")},
            {"max_entries": 0},
            {"max_entries": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                WebhookReplayGuard(**kwargs)

    def test_malformed_payload_does_not_consume_event_id(self) -> None:
        guard = WebhookReplayGuard()
        body = b'{"memberCardId":true}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))

        with self.assertRaises(WebhookVerificationException):
            WebhookVerifier.parse(
                "CARD_STATUS", "evt-invalid-payload", body, signature, PUBLIC_KEY_PEM,
                replay_guard=guard,
            )
        self.assertTrue(guard.accept("evt-invalid-payload"))

    def test_invalid_decimal_payload_is_wrapped(self) -> None:
        body = b'{"tradeAmount":"not-a-decimal"}'
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))

        with self.assertRaisesRegex(WebhookVerificationException, "payload is invalid"):
            WebhookVerifier.parse("CARD_TRANSACTIONS", "evt-invalid-decimal", body, signature, PUBLIC_KEY_PEM)

    def test_invalid_event_raises(self) -> None:
        body = b"{}"
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        with self.assertRaises(WebhookVerificationException):
            WebhookVerifier.parse("UNKNOWN", "evt", body, signature, PUBLIC_KEY_PEM)

    def test_rejects_oversized_body_before_signature_and_replay_guard(self) -> None:
        body = b"{}"
        signature = sign(body, read_private_key(PRIVATE_KEY_PEM))
        guard = WebhookReplayGuard()
        with self.assertRaisesRegex(WebhookVerificationException, "exceeded max_body_bytes"):
            WebhookVerifier.parse(
                "CARD_STATUS",
                "evt-oversized",
                body,
                signature,
                PUBLIC_KEY_PEM,
                replay_guard=guard,
                max_body_bytes=1,
            )
        self.assertTrue(guard.accept("evt-oversized"))

    def test_rejects_invalid_body_limit(self) -> None:
        with self.assertRaises(ValueError):
            WebhookVerifier.parse(
                "CARD_STATUS", "evt", b"{}", "signature", PUBLIC_KEY_PEM, max_body_bytes=0
            )


if __name__ == "__main__":
    unittest.main()
