"""Webhook signature verification and typed payload parsing."""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from .crypto import RsaPublicKey, read_public_key, verify
from .models import (
    CardOpenStatusWebhook,
    CardStatusWebhook,
    RechargeCardTransferStatusWebhook,
    SharedAccountOpenStatusWebhook,
    TransactionWebhook,
)
from .codec import decode_value


_DEFAULT_MAX_BODY_BYTES = 16 * 1024 * 1024


class WebhookEventType(str, Enum):
    """Supported values of the webhook ``event`` header."""

    CARD_TRANSACTIONS = "CARD_TRANSACTIONS"
    CARD_SETTLE_STATUS = "CARD_SETTLE_STATUS"
    CARD_STATUS = "CARD_STATUS"
    CARD_OPEN_STATUS = "CARD_OPEN_STATUS"
    CARD_RECHARGE_STATUS = "CARD_RECHARGE_STATUS"
    CARD_WITHDRAW_STATUS = "CARD_WITHDRAW_STATUS"
    CARD_LIMIT_STATUS = "CARD_LIMIT_STATUS"
    SHARED_ACCOUNT_OPEN_STATUS = "SHARED_ACCOUNT_OPEN_STATUS"
    SHARE_ACCOUNT_FUND_TRANSACTIONS = "SHARE_ACCOUNT_FUND_TRANSACTIONS"


class WebhookVerificationException(RuntimeError):
    """Raised when webhook headers, signature, or payload are invalid."""


class WebhookReplayGuard:
    """Thread-safe process-local event-ID replay guard.

    Use durable application-level idempotency for protection across processes.
    """

    __slots__ = ("_ttl_seconds", "_max_entries", "_entries", "_lock")

    def __init__(self, *, ttl_seconds: float = 300.0, max_entries: int = 10_000) -> None:
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, (int, float))
            or not math.isfinite(ttl_seconds)
            or ttl_seconds <= 0
        ):
            raise ValueError("ttl_seconds must be a finite number greater than zero")
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = max_entries
        self._entries: dict[str, float] = {}
        self._lock = threading.Lock()

    def accept(self, event_id: str) -> bool:
        """Record an event ID; return ``False`` when it was recently recorded."""
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id must not be blank")
        now = time.monotonic()
        cutoff = now - self._ttl_seconds
        with self._lock:
            expired = [key for key, timestamp in self._entries.items() if timestamp <= cutoff]
            for key in expired:
                del self._entries[key]
            if event_id in self._entries:
                return False
            while len(self._entries) >= self._max_entries:
                self._entries.pop(next(iter(self._entries)))
            self._entries[event_id] = now
            return True


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """Verified webhook event retaining the exact bytes used for verification."""

    type: WebhookEventType
    event_id: str
    raw_body: bytes
    signature: str
    payload: Any

    def __post_init__(self) -> None:
        if not isinstance(self.type, WebhookEventType):
            raise TypeError("type must be WebhookEventType")
        if not isinstance(self.raw_body, bytes):
            raise TypeError("raw_body must be bytes")
        object.__setattr__(self, "raw_body", bytes(self.raw_body))

    @property
    def raw_body_utf8(self) -> str:
        """Return the exact verified body decoded as UTF-8."""
        return self.raw_body.decode("utf-8")

    def __repr__(self) -> str:
        return (
            f"WebhookEvent(type={self.type!r}, event_id={self.event_id!r}, "
            "raw_body='<redacted>', signature='<redacted>', payload='<redacted>')"
        )


class WebhookVerifier:
    """Verify exact webhook request bytes and parse supported event payloads."""

    @staticmethod
    def verify(
        raw_body: bytes | str,
        signature: str,
        public_key: RsaPublicKey | str,
        *,
        max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    ) -> bool:
        """Verify a Base64 SHA256withRSA signature without parsing the body."""
        limit = _validate_max_body_bytes(max_body_bytes)
        if raw_body is None:
            return False
        if isinstance(raw_body, str):
            try:
                body = raw_body.encode("utf-8")
            except UnicodeEncodeError:
                return False
        else:
            body = raw_body
        if not isinstance(body, bytes) or len(body) > limit:
            return False
        key = read_public_key(public_key) if isinstance(public_key, str) else public_key
        return verify(body, signature, key)

    @staticmethod
    def parse(
        event: str | WebhookEventType,
        event_id: str,
        raw_body: bytes | str,
        signature: str,
        public_key: RsaPublicKey | str,
        *,
        replay_guard: WebhookReplayGuard | None = None,
        max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    ) -> WebhookEvent:
        """Verify headers and exact body bytes, then decode the event payload."""
        limit = _validate_max_body_bytes(max_body_bytes)
        event_name = event.value if isinstance(event, WebhookEventType) else event
        _require_header(event_name, "event")
        _require_header(event_id, "event_id")
        _require_header(signature, "sign")
        if raw_body is None:
            raise WebhookVerificationException("Webhook raw body must not be null")
        if isinstance(raw_body, str):
            try:
                body = raw_body.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise WebhookVerificationException(
                    "Webhook raw body must be valid UTF-8 text"
                ) from exc
        else:
            body = raw_body
        if not isinstance(body, bytes):
            raise WebhookVerificationException("Webhook raw body must be bytes or UTF-8 text")
        if len(body) > limit:
            raise WebhookVerificationException("Webhook raw body exceeded max_body_bytes")
        try:
            event_type = WebhookEventType(event_name)
        except ValueError as exc:
            raise WebhookVerificationException(f"Unsupported webhook event: {event_name}") from exc
        try:
            valid = WebhookVerifier.verify(
                body, signature, public_key, max_body_bytes=limit
            )
        except (TypeError, ValueError) as exc:
            raise WebhookVerificationException("Webhook public key is invalid") from exc
        if not valid:
            raise WebhookVerificationException("Webhook signature is invalid")
        payload_type = _payload_type(event_type)
        try:
            decoded = json.loads(body.decode("utf-8"), parse_float=Decimal)
            payload = decode_value(decoded, payload_type)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise WebhookVerificationException(
                f"Webhook payload is invalid for {payload_type.__name__}"
            ) from exc
        if replay_guard is not None and not replay_guard.accept(event_id):
            raise WebhookVerificationException("Webhook event_id has already been processed")
        return WebhookEvent(event_type, event_id, body, signature, payload)


def _payload_type(event_type: WebhookEventType) -> type[Any]:
    if event_type is WebhookEventType.CARD_OPEN_STATUS:
        return CardOpenStatusWebhook
    if event_type is WebhookEventType.CARD_STATUS:
        return CardStatusWebhook
    if event_type in {
        WebhookEventType.CARD_RECHARGE_STATUS,
        WebhookEventType.CARD_WITHDRAW_STATUS,
        WebhookEventType.CARD_LIMIT_STATUS,
    }:
        return RechargeCardTransferStatusWebhook
    if event_type is WebhookEventType.SHARED_ACCOUNT_OPEN_STATUS:
        return SharedAccountOpenStatusWebhook
    return TransactionWebhook


def _require_header(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WebhookVerificationException(f"Webhook {name} header must not be blank")


def _validate_max_body_bytes(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("max_body_bytes must be a positive integer")
    return value
