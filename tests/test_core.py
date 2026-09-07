"""Core transport, validation, and cryptography tests."""

from __future__ import annotations

import json
import http.cookiejar
import logging
import unittest
import base64
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from unittest import mock

import structlog

from luminal_open_api_sdk import (
    LuminalApiException,
    LuminalOpenApiClient,
    read_private_key,
    read_public_key,
    serialize_json,
    serialize_json_for_signature,
    sign,
    verify,
)
from luminal_open_api_sdk.codec import decode_value
from luminal_open_api_sdk.crypto import RsaPrivateKey, RsaPublicKey
from luminal_open_api_sdk.models import CardIdRequest, Long, MemberCardPageRequest, WalletInfoRequest

from tests.support import FakeOpener, FakeResponse, PRIVATE_KEY_PEM, PUBLIC_KEY_PEM, SequenceOpener, client_for
from tests.share_card_sandbox_open_api_integration_test import _sandbox_urlopen
from luminal_open_api_sdk.transport import HttpTransport


@dataclass(frozen=True)
class LongPayload:
    amount: Long
    member_no: Long
    positive_interior: Long
    positive_boundary: Long
    negative_interior: Long
    negative_boundary: Long
    items: list[Long]


class RsaSigningTest(unittest.TestCase):
    def test_signature_covers_exact_bytes(self) -> None:
        private_key = read_private_key(PRIVATE_KEY_PEM)
        public_key = read_public_key(PUBLIC_KEY_PEM)
        signature = sign(b'{"amount":1}', private_key)
        self.assertTrue(verify(b'{"amount":1}', signature, public_key))
        self.assertFalse(verify(b'{ "amount": 1 }', signature, public_key))

    def test_rejects_signature_value_outside_rsa_modulus(self) -> None:
        private_key = read_private_key(PRIVATE_KEY_PEM)
        public_key = read_public_key(PUBLIC_KEY_PEM)
        for index in range(128):
            content = f"payload-{index}".encode()
            signature = sign(content, private_key)
            raw_signature = base64.b64decode(signature)
            signature_value = int.from_bytes(raw_signature, "big")
            if signature_value + public_key.modulus < 1 << (8 * len(raw_signature)):
                forged = base64.b64encode(
                    (signature_value + public_key.modulus).to_bytes(len(raw_signature), "big")
                ).decode("ascii")
                self.assertFalse(verify(content, forged, public_key))
                return
        self.fail("Could not construct an in-range encoded signature congruent modulo the RSA modulus")

    def test_private_key_repr_does_not_expose_key_material(self) -> None:
        private_key = read_private_key(PRIVATE_KEY_PEM)

        self.assertEqual("RsaPrivateKey(<redacted>)", repr(private_key))
        self.assertNotIn(str(private_key.private_exponent), repr(private_key))

    def test_rejects_invalid_rsa_key_components(self) -> None:
        with self.assertRaisesRegex(ValueError, "modulus"):
            sign(b"payload", RsaPrivateKey(2, 1))
        self.assertFalse(verify(b"payload", "bad", RsaPublicKey(2, 2)))


class SerializationTest(unittest.TestCase):
    def test_long_values_use_the_javascript_safe_integer_rule(self) -> None:
        payload = json.loads(
            serialize_json(LongPayload(
                amount=100,
                member_no=2_064_991_632_710_991_874,
                positive_interior=9_007_199_254_740_990,
                positive_boundary=9_007_199_254_740_991,
                negative_interior=-9_007_199_254_740_990,
                negative_boundary=-9_007_199_254_740_991,
                items=[
                    1,
                    9_007_199_254_740_990,
                    9_007_199_254_740_991,
                    -9_007_199_254_740_990,
                    -9_007_199_254_740_991,
                    (1 << 63) - 1,
                    -(1 << 63),
                ],
            ))
        )
        self.assertEqual(100, payload["amount"])
        self.assertEqual("2064991632710991874", payload["memberNo"])
        self.assertEqual(9_007_199_254_740_990, payload["positiveInterior"])
        self.assertEqual("9007199254740991", payload["positiveBoundary"])
        self.assertEqual(-9_007_199_254_740_990, payload["negativeInterior"])
        self.assertEqual("-9007199254740991", payload["negativeBoundary"])
        self.assertEqual(
            [
                1,
                9_007_199_254_740_990,
                "9007199254740991",
                -9_007_199_254_740_990,
                "-9007199254740991",
                "9223372036854775807",
                "-9223372036854775808",
            ],
            payload["items"],
        )

    def test_signature_json_keeps_typed_long_values_numeric(self) -> None:
        payload = json.loads(serialize_json_for_signature(LongPayload(
            amount=100,
            member_no=2_064_991_632_710_991_874,
            positive_interior=9_007_199_254_740_990,
            positive_boundary=9_007_199_254_740_991,
            negative_interior=-9_007_199_254_740_990,
            negative_boundary=-9_007_199_254_740_991,
            items=[(1 << 63) - 1, -(1 << 63)],
        )))

        self.assertEqual(2_064_991_632_710_991_874, payload["memberNo"])
        self.assertEqual(9_007_199_254_740_991, payload["positiveBoundary"])
        self.assertEqual(-9_007_199_254_740_991, payload["negativeBoundary"])
        self.assertEqual([(1 << 63) - 1, -(1 << 63)], payload["items"])


class LongRequestValidationTest(unittest.TestCase):
    def test_rejects_invalid_typed_long_values(self) -> None:
        for value, error_type in (
            (True, TypeError),
            ("2147483648", TypeError),
            (1 << 63, ValueError),
            (-(1 << 63) - 1, ValueError),
        ):
            with self.subTest(value=value), self.assertRaises(error_type):
                serialize_json(LongPayload(
                    amount=value,
                    member_no=1,
                    positive_interior=1,
                    positive_boundary=1,
                    negative_interior=1,
                    negative_boundary=1,
                    items=[],
                ))

class IntegerSerializationTest(unittest.TestCase):
    def test_untyped_integers_remain_numbers(self) -> None:
        self.assertEqual(
            b'{"amount":100,"memberNo":2064991632710991874}',
            serialize_json({
                "amount": 100,
                "memberNo": 2_064_991_632_710_991_874,
            }),
        )

    def test_java_integer_fields_remain_numbers(self) -> None:
        self.assertEqual(
            b'{"pageSize":2147483648}',
            serialize_json(WalletInfoRequest(page_size=2_147_483_648)),
        )

    def test_typed_long_lists_keep_int32_overflow_as_numbers(self) -> None:
        self.assertEqual(
            b'{"cardGroups":[1,2147483648]}',
            serialize_json(MemberCardPageRequest(card_groups=[1, 2_147_483_648])),
        )


class ResponseDecodingTest(unittest.TestCase):
    def test_java_local_date_arrays_decode_to_dates(self) -> None:
        expected = date(1990, 1, 15)

        self.assertEqual(expected, decode_value([1990, 1, 15], date))
        self.assertEqual(expected, decode_value([1990, 1, 15], date | None))

    def test_datetime_timestamps_decode_milliseconds_and_microseconds(self) -> None:
        self.assertEqual(
            datetime(2026, 7, 17, 9, 44, 9, tzinfo=timezone.utc),
            decode_value(1_784_281_449_000, datetime),
        )
        self.assertEqual(
            datetime(2026, 7, 1, 7, 18, 48, tzinfo=timezone.utc),
            decode_value(1_782_890_328_000_000, datetime),
        )

    def test_long_strings_decode_to_python_ints(self) -> None:
        client, _ = client_for({"memberCardId": "2064991632710991874"})
        result = client.cards.limit(CardIdRequest(member_card_id=1))

        self.assertEqual(2_064_991_632_710_991_874, result.member_card_id)
        self.assertIsInstance(result.member_card_id, int)

    def test_paginated_long_total_decodes_to_python_int(self) -> None:
        client, _ = client_for({"total": "2064991632710991874", "list": []})
        result = client.accounts.list(WalletInfoRequest())

        self.assertEqual(2_064_991_632_710_991_874, result.total)
        self.assertIsInstance(result.total, int)

    def test_member_card_create_time_is_epoch_milliseconds(self) -> None:
        body = json.dumps({
            "code": 0,
            "msg": "success",
            "data": {"list": [{"createTime": "2064991632710991874"}], "total": 1},
        }).encode()
        client = LuminalOpenApiClient(
            "https://api.example.test",
            "token",
            opener=FakeOpener(FakeResponse(body)),
        )
        result = client.cards.list(MemberCardPageRequest())

        self.assertEqual(2_064_991_632_710_991_874, result.list[0].create_time)

    def test_rejects_invalid_java_long_values(self) -> None:
        for value in (True, "false", 1.5, str(1 << 63)):
            client, _ = client_for({"memberCardId": value})
            with self.subTest(value=value), self.assertRaisesRegex(
                LuminalApiException, "could not be decoded"
            ):
                client.cards.limit(CardIdRequest(member_card_id=1))

    def test_rejects_non_array_paginated_list(self) -> None:
        client, _ = client_for({"total": 1, "list": {}})

        with self.assertRaisesRegex(LuminalApiException, "could not be decoded"):
            client.accounts.list(WalletInfoRequest())


class TransportErrorTest(unittest.TestCase):
    def test_retries_http_200_business_401_with_fresh_token(self) -> None:
        opener = SequenceOpener(
            FakeResponse(b'{"code":401,"msg":"Account is not logged in","data":null}'),
            FakeResponse(b'{"code":0,"msg":"success","data":true}'),
        )
        refreshes = []

        def token_provider(force_refresh: bool) -> str:
            refreshes.append(force_refresh)
            return "fresh-token" if force_refresh else "cached-token"

        transport = HttpTransport(
            "https://api.example.test",
            opener=opener,
            bearer_token_provider=token_provider,
            retry_unauthorized=1,
            log_http=False,
        )

        self.assertTrue(transport.post("/test"))
        self.assertEqual([False, True], refreshes)
        self.assertEqual(2, len(opener.requests))
        self.assertEqual("Bearer fresh-token", opener.requests[-1].get_header("Authorization"))

    def test_does_not_refresh_unauthorized_without_token_provider(self) -> None:
        opener = SequenceOpener(FakeResponse(b'{"code":401,"msg":"Account is not logged in","data":null}'))
        transport = HttpTransport(
            "https://api.example.test",
            "fixed-token",
            opener=opener,
            retry_unauthorized=1,
            log_http=False,
        )

        with self.assertRaisesRegex(LuminalApiException, "Account is not logged in") as context:
            transport.post("/test")

        self.assertEqual(401, context.exception.api_code)
        self.assertEqual(1, len(opener.requests))

    def test_seconds_expiry_refreshes_with_token_endpoint_at_half_ttl(self) -> None:
        def response(data):
            return FakeResponse(json.dumps({"code": 0, "msg": "success", "data": data}).encode())

        opener = SequenceOpener(
            response({"accessToken": "token-a", "expiresTime": 2000}),
            response({"total": 0, "list": []}),
            response({"accessToken": "token-b", "expiresTime": 2600}),
            response({"total": 0, "list": []}),
        )
        client = LuminalOpenApiClient(
            "https://api.example.test",
            app_id="app",
            app_secret="secret",
            opener=opener,
            log_http=False,
        )

        with mock.patch("luminal_open_api_sdk.client.time.time", side_effect=[1000.0, 1600.0, 1600.0, 1600.0]):
            client.accounts.list(WalletInfoRequest())
            client.accounts.list(WalletInfoRequest())

        paths = [urllib.parse.urlparse(request.full_url).path for request in opener.requests]
        self.assertEqual(
            [
                "/open-api/v1/auth/token",
                "/open-api/v1/accounts",
                "/open-api/v1/auth/token",
                "/open-api/v1/accounts",
            ],
            paths,
        )
        self.assertNotIn("/open-api/v1/auth/refresh-token", paths)
        self.assertEqual("Bearer token-b", opener.requests[-1].get_header("Authorization"))


    def test_rejects_malformed_response_envelope(self) -> None:
        opener = FakeOpener(FakeResponse(b"{}"))
        client = LuminalOpenApiClient("https://api.example.test", "token", opener=opener)

        with self.assertRaisesRegex(LuminalApiException, "missing an integer code"):
            client.accounts.list(WalletInfoRequest())

    def test_raises_for_business_error(self) -> None:
        body = json.dumps({"code": 1001, "msg": "invalid request", "data": None}).encode()
        opener = FakeOpener(FakeResponse(body))
        client = LuminalOpenApiClient("https://api.example.test", "token", opener=opener)

        with self.assertRaises(LuminalApiException) as context:
            client.auth.logout()

        self.assertEqual(1001, context.exception.api_code)
        self.assertEqual("invalid request", str(context.exception))

    def test_raises_for_http_error(self) -> None:
        opener = FakeOpener(FakeResponse(b"server error", status=503))
        client = LuminalOpenApiClient("https://api.example.test", "token", opener=opener)

        with self.assertRaises(LuminalApiException) as context:
            client.auth.logout()

        self.assertEqual(503, context.exception.http_status)

    def test_closes_http_response_after_reading(self) -> None:
        client, opener = client_for(True)

        self.assertTrue(client.auth.logout())
        self.assertTrue(opener.response.closed)

    def test_exposes_exact_raw_response_body(self) -> None:
        client, _ = client_for(True)

        self.assertTrue(client.auth.logout())
        self.assertEqual(b'{"code": 0, "msg": "success", "data": true}', client.transport.last_response_body)

    def test_truncates_response_body_in_exceptions(self) -> None:
        opener = FakeOpener(FakeResponse(b"x" * 9_000))
        client = LuminalOpenApiClient(
            "https://api.example.test",
            "token",
            opener=opener,
        )

        with self.assertRaises(LuminalApiException) as context:
            client.auth.logout()

        self.assertIsNotNone(context.exception.response_body)
        self.assertTrue(context.exception.response_body.endswith("...[truncated]"))
        self.assertLess(len(context.exception.response_body), 9_000)

    def test_rejects_oversized_response(self) -> None:
        opener = FakeOpener(FakeResponse(b"123456"))
        client = LuminalOpenApiClient(
            "https://api.example.test",
            "token",
            max_response_bytes=5,
            opener=opener,
        )

        with self.assertRaisesRegex(LuminalApiException, "exceeded max_response_bytes"):
            client.auth.logout()

    def test_closes_response_after_oversized_response(self) -> None:
        opener = FakeOpener(FakeResponse(b"123456"))
        client = LuminalOpenApiClient(
            "https://api.example.test",
            "token",
            max_response_bytes=5,
            opener=opener,
        )

        with self.assertRaises(LuminalApiException):
            client.auth.logout()

        self.assertTrue(opener.response.closed)

    def test_rejects_non_boolean_action_result(self) -> None:
        client, _ = client_for("false")

        with self.assertRaisesRegex(LuminalApiException, "could not be decoded"):
            client.auth.logout()


class TransportLoggingTest(unittest.TestCase):
    def test_decode_failure_logs_raw_response(self) -> None:
        body = b'{"code":0,"data":{"birthDate":[1990,1,15]}}'
        transport = HttpTransport(
            "https://api.example.test",
            bearer_token="secret-token",
            opener=FakeOpener(FakeResponse(body)),
        )

        with self.assertLogs("luminal_open_api_sdk.transport", level="INFO") as captured:
            with self.assertRaisesRegex(LuminalApiException, "could not be decoded"):
                transport.post_serialized("/test", None, decoder=lambda value: value["missing"])

        raw_records = [record for record in captured.records if "HTTP raw response" in record.getMessage()]
        self.assertEqual(1, len(raw_records))
        message = raw_records[0].getMessage()
        self.assertIn("HTTP raw response url=\"https://api.example.test/test\" status=200", message)
        self.assertIn("birthDate", message)
        self.assertIn("[1990,1,15]", message)

    def test_raw_http_logging_precedes_redacted_response_logging(self) -> None:
        body = b'{"code":0,"data":{"status":"PENDING"}}'
        transport = HttpTransport(
            "https://api.example.test",
            bearer_token="secret-token",
            opener=FakeOpener(FakeResponse(body)),
            log_raw_http=True,
        )

        with self.assertLogs("luminal_open_api_sdk.transport", level="INFO") as captured:
            self.assertEqual({"status": "PENDING"}, transport.post_serialized("/test", None))

        self.assertEqual(3, len(captured.records))
        messages = [record.getMessage() for record in captured.records]
        self.assertIn("HTTP request", messages[0])
        self.assertIn("HTTP raw response", messages[1])
        self.assertIn("status", messages[1])
        self.assertIn("PENDING", messages[1])
        self.assertIn("HTTP response", messages[2])

    def test_http_logging_is_enabled_by_default(self) -> None:
        transport = HttpTransport(
            "https://api.example.test",
            bearer_token="secret-token",
            opener=FakeOpener(FakeResponse(b'{"code":0,"data":true}')),
        )

        with self.assertLogs("luminal_open_api_sdk.transport", level="INFO") as captured:
            self.assertTrue(transport.post_serialized("/test", None))

        self.assertEqual(2, len(captured.records))
        lines = [record.getMessage() for record in captured.records]
        self.assertIn('HTTP request method=POST url="https://api.example.test/test"', lines[0])
        self.assertIn(
            'HTTP response url="https://api.example.test/test" status=200',
            lines[1],
        )
        self.assertIn('body=""', lines[0])

    def test_http_logging_can_be_disabled(self) -> None:
        logger = mock.Mock()
        transport = HttpTransport(
            "https://api.example.test",
            bearer_token="secret-token",
            opener=FakeOpener(FakeResponse(b'{"code":0,"data":true}')),
            log_http=False,
            logger=logger,
        )

        with mock.patch.object(HttpTransport, "_redact_log_body", side_effect=AssertionError("must not redact")):
            self.assertTrue(transport.post_serialized("/test", None))

        logger.info.assert_not_called()

    def test_custom_structlog_stdlib_logger_is_preserved(self) -> None:
        logger_name = "tests.transport.custom"
        logger = structlog.wrap_logger(
            logging.getLogger(logger_name),
            processors=[structlog.stdlib.render_to_log_kwargs],
            wrapper_class=structlog.stdlib.BoundLogger,
        )
        client = LuminalOpenApiClient(
            "https://api.example.test",
            "secret-token",
            opener=FakeOpener(FakeResponse(b'{"code":0,"data":true}')),
            logger=logger,
        )

        with self.assertLogs(logger_name, level="INFO") as captured:
            self.assertTrue(client.transport.post_serialized("/test", None))

        self.assertEqual(2, len(captured.records))
        self.assertIs(client.transport.logger, logger)
        self.assertIs(client.with_bearer_token("other-token").transport.logger, logger)

    def test_request_and_response_logs_redact_sensitive_data(self) -> None:
        opener = FakeOpener(FakeResponse(
            b'{"code":0,"data":{"accessToken":"response-access-secret","refreshToken":"response-refresh-secret","appSecret":"response-app-secret","nested":{"cvv":"response-cvv-secret","cardNo":"response-card-secret","cardNumber":"response-card-number-secret"}}}'
        ))
        transport = HttpTransport(
            "https://api.example.test",
            bearer_token="bearer-secret",
            opener=opener,
        )
        request_body = (
            b'{"refreshToken":"request-refresh-secret","nested":{"CVV":"request-cvv-secret"},'
            b'"items":[{"cardNumber":"request-card-secret"}]}'
        )
        request_headers = {
            "cOoKiE": "session=cookie-secret",
            "SiGn": "signature-secret",
            "sEt-CoOkIe": "session=set-cookie-secret",
        }
        original_headers = request_headers.copy()

        with self.assertLogs("luminal_open_api_sdk.transport", level="INFO") as captured:
            transport.post_serialized(
                "/test",
                request_body,
                headers=request_headers,
            )

        self.assertEqual(2, len(captured.records))
        request, response = (record.getMessage() for record in captured.records)
        self.assertIn('HTTP request method=POST url="https://api.example.test/test"', request)
        self.assertIn('headers={"Accept":"application/json"', request)
        self.assertIn('"Authorization":"<redacted>"', request)
        self.assertIn('"cOoKiE":"<redacted>"', request)
        self.assertIn('"SiGn":"<redacted>"', request)
        self.assertIn('"sEt-CoOkIe":"<redacted>"', request)
        self.assertIn('HTTP response url="https://api.example.test/test" status=200', response)
        for secret in (
            "bearer-secret",
            "cookie-secret",
            "signature-secret",
            "set-cookie-secret",
            "request-refresh-secret",
            "request-cvv-secret",
            "request-card-secret",
            "response-access-secret",
            "response-refresh-secret",
            "response-app-secret",
            "response-cvv-secret",
            "response-card-secret",
            "response-card-number-secret",
        ):
            self.assertNotIn(secret, request + response)
        self.assertIn("<redacted>", request)
        self.assertIn("<redacted>", response)
        self.assertNotRegex(request + response, "[\r\n]")
        self.assertEqual(original_headers, request_headers)
        self.assertIs(request_body, opener.request.data)
        sent_headers = {name.lower(): value for name, value in opener.request.header_items()}
        self.assertEqual("session=cookie-secret", sent_headers["cookie"])
        self.assertEqual("signature-secret", sent_headers["sign"])
        self.assertEqual("session=set-cookie-secret", sent_headers["set-cookie"])

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.assertRegex(
            formatter.format(captured.records[0]),
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} INFO luminal_open_api_sdk\.transport transport\.py:\d+ HTTP request ",
        )

    def test_non_json_response_logs_only_byte_length(self) -> None:
        transport = HttpTransport(
            "https://api.example.test",
            bearer_token="token",
            opener=FakeOpener(FakeResponse(b"not-json")),
        )

        with self.assertLogs("luminal_open_api_sdk.transport", level="INFO") as captured:
            with self.assertRaisesRegex(LuminalApiException, "invalid JSON"):
                transport.post_serialized("/test", None)

        logs = " ".join(record.getMessage() for record in captured.records)
        self.assertNotIn("not-json", logs)
        self.assertIn("<non-json 8 bytes>", logs)


class ClientValidationTest(unittest.TestCase):
    def test_raw_response_logging_survives_bearer_token_switch(self) -> None:
        client = LuminalOpenApiClient(
            "https://api.example.test",
            "token",
            log_raw_http=True,
        )

        self.assertTrue(client.transport.log_raw_http)
        self.assertTrue(client.with_bearer_token("other-token").transport.log_raw_http)

    def test_default_transport_uses_shared_cookie_jar(self) -> None:
        client = LuminalOpenApiClient("https://api.example.test", "token", log_http=False)
        opener = client.transport._opener
        director = getattr(opener, "__self__", None)

        self.assertTrue(any(
            isinstance(handler, urllib.request.HTTPCookieProcessor)
            and isinstance(handler.cookiejar, http.cookiejar.CookieJar)
            for handler in director.handlers
        ))
        self.assertIs(opener, client.with_bearer_token("other-token").transport._opener)

    def test_default_response_limit_is_one_mib(self) -> None:
        client = LuminalOpenApiClient("https://api.example.test", "token", log_http=False)
        self.assertEqual(1024 * 1024, client.transport.max_response_bytes)

    def test_rejects_invalid_base_url(self) -> None:
        for base_url in (
            "not-a-url",
            "https://user:pass@example.test",
            "https://example.test:bad",
            "https://example.test:65536",
            " https://example.test",
            "https://example.test ",
            "https://example.test/\t",
            "https://example.test/\nhealth",
        ):
            with self.subTest(base_url=base_url), self.assertRaises(ValueError):
                LuminalOpenApiClient(base_url)

    def test_protected_request_requires_bearer_token(self) -> None:
        opener = FakeOpener(FakeResponse(b'{"code":0,"data":true}'))
        client = LuminalOpenApiClient("https://api.example.test", opener=opener)

        with self.assertRaisesRegex(ValueError, "bearer_token must not be blank"):
            client.accounts.list(WalletInfoRequest())

        self.assertIsNone(opener.request)
    def test_rejects_invalid_timeout(self) -> None:
        for timeout in (True, 0, -1, float("inf"), "30"):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(
                ValueError, "timeout must be a finite number"
            ):
                LuminalOpenApiClient("https://api.example.test", "token", timeout=timeout)

    def test_rejects_invalid_max_response_bytes(self) -> None:
        for value in (True, 0, -1, 1.5, "1024"):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "max_response_bytes must be a positive integer"
            ):
                LuminalOpenApiClient(
                    "https://api.example.test",
                    "token",
                    max_response_bytes=value,
                )

    def test_rejects_invalid_header_names_and_values(self) -> None:
        client, opener = client_for(True)
        invalid_headers = (
            {"": "value"},
            {"X Bad": "value"},
            {"X-Test": "line\nvalue"},
            {"X-Test": "value\x00"},
            {"X-Test": "value\x1f"},
            {"X-Test": "value\x7f"},
        )

        for headers in invalid_headers:
            with self.subTest(headers=headers), self.assertRaisesRegex(
                (TypeError, ValueError), "headers"
            ):
                client.transport.post("/test", headers=headers)

        self.assertIsNone(opener.request)

    def test_protected_authorization_header_cannot_be_overridden(self) -> None:
        client, opener = client_for(True)

        with self.assertRaisesRegex(ValueError, "Authorization header is managed"):
            client.transport.post("/test", headers={"authorization": "Bearer forged"})

        self.assertIsNone(opener.request)

    def test_rejects_unsafe_endpoint_paths(self) -> None:
        client, opener = client_for(True)

        for path in ("test", "//other-host", "/test?redirect=1", "/test#fragment", "/test\\secret"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "path"):
                client.transport.post(path)

        self.assertIsNone(opener.request)


class SandboxTlsRetryTest(unittest.TestCase):
    def test_retries_only_tls_handshake_eof(self) -> None:
        response = object()
        calls = 0

        def tls_then_success(request, *, timeout):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise urllib.error.URLError(ssl.SSLEOFError(8, "handshake EOF"))
            return response

        self.assertIs(
            _sandbox_urlopen(object(), timeout=1, _urlopen=tls_then_success, _sleep=lambda _: None),
            response,
        )
        self.assertEqual(calls, 3)

        calls = 0

        def timeout_error(request, *, timeout):
            nonlocal calls
            calls += 1
            raise urllib.error.URLError(TimeoutError())

        with self.assertRaises(urllib.error.URLError):
            _sandbox_urlopen(object(), timeout=1, _urlopen=timeout_error, _sleep=lambda _: None)
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()

