"""Standalone HTTP and canonical JSON transport for the Luminal SDK."""

from __future__ import annotations

import json
import http.cookiejar
import logging
import math
import sys
import threading
import types
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Callable, Union, get_args, get_origin, get_type_hints


_MISSING = object()
_INT64_MIN = -(1 << 63)
_INT64_MAX = (1 << 63) - 1
_JS_SAFE_INTEGER_BOUNDARY = (1 << 53) - 1
_DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_ERROR_BODY_BYTES = 8 * 1024
_ERROR_BODY_TRUNCATION_MARKER = "...[truncated]"
_DEFAULT_USER_AGENT = "luminal-open-api-python-sdk/1.0"
_HTTP_HEADER_NAME_CHARS = frozenset("!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_SENSITIVE_LOG_HEADERS = frozenset({"authorization", "cookie", "set-cookie", "sign"})
_SENSITIVE_LOG_BODY_KEYS = frozenset(
    {"accesstoken", "refreshtoken", "appsecret", "cvv", "cardno", "cardnumber", "verifycode"}
)
_LOGGER = logging.getLogger(__name__)


def _type_hints(target: type[Any]) -> dict[str, Any]:
    try:
        return get_type_hints(
            target,
            globalns=vars(sys.modules[target.__module__]),
            localns={},
            include_extras=True,
        )
    except (NameError, TypeError):
        return {}


def _serialize_java_long(value: Any, for_signature: bool = False) -> int | str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Java Long values must be Python integers")
    if value < _INT64_MIN or value > _INT64_MAX:
        raise ValueError("Java Long is outside the signed 64-bit range")
    if for_signature:
        return value
    return value if -_JS_SAFE_INTEGER_BOUNDARY < value < _JS_SAFE_INTEGER_BOUNDARY else str(value)

def _is_java_long(annotation: Any) -> bool:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        return len(args) > 1 and "java-long" in args[1:]
    if origin in (Union, types.UnionType):
        return any(_is_java_long(option) for option in get_args(annotation))
    return False


def _without_none(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        options = [option for option in get_args(annotation) if option is not type(None)]
        if len(options) == 1:
            return options[0]
    return annotation


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])

def to_wire(value: Any, annotation: Any = Any, *, for_signature: bool = False) -> Any:
    """Convert SDK values to canonical JSON-compatible values, omitting nulls.

    Only fields typed as the SDK's Java-compatible ``Long`` use the JavaScript
    safe-integer number/string split. Other Python integers remain JSON numbers.
    """

    if value is None:
        return None
    if _is_java_long(annotation):
        return _serialize_java_long(value, for_signature)
    if is_dataclass(value):
        hints = _type_hints(type(value))
        return {
            _camel_case(field.name): to_wire(
                getattr(value, field.name),
                hints.get(field.name, field.type),
                for_signature=for_signature,
            )
            for field in fields(value)
            if not field.metadata.get("wire_ignore") and getattr(value, field.name) is not None
        }
    if isinstance(value, Enum):
        return to_wire(value.value, for_signature=for_signature)
    if isinstance(value, dict):
        args = get_args(_without_none(annotation))
        item_annotation = args[1] if len(args) == 2 else Any
        return {
            str(key): to_wire(item, item_annotation, for_signature=for_signature)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        args = get_args(_without_none(annotation))
        item_annotation = args[0] if args else Any
        return [to_wire(item, item_annotation, for_signature=for_signature) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Decimal values must be finite")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("Float values must be finite")
    return value


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Decimal):
        return format(value, "f") if value.as_tuple().exponent < 0 else str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        entries = sorted(value.items(), key=lambda item: str(item[0]))
        return "{" + ",".join(
            _encode(str(key)) + ":" + _encode(item) for key, item in entries
        ) + "}"
    raise TypeError(f"Value of type {type(value).__name__} is not JSON serializable")


def serialize_json(value: Any) -> bytes:
    """Serialize a value using sorted keys, compact separators, UTF-8, and no nulls."""

    return _encode(to_wire(value)).encode("utf-8")


def serialize_json_for_signature(value: Any) -> bytes:
    """Serialize canonical signing bytes with typed Java Long values kept numeric."""

    return _encode(to_wire(value, for_signature=True)).encode("utf-8")


class LuminalApiException(RuntimeError):
    """HTTP, transport, response-envelope, or business-code failure.

    ``response_body`` is UTF-8 text capped for safe exception retention.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int = -1,
        api_code: int | None = None,
        response_body: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.api_code = api_code
        self.response_body = response_body
        if cause is not None:
            self.__cause__ = cause


class HttpTransport:
    """Small urllib-based transport with no third-party runtime dependency."""

    def __init__(
        self,
        base_url: str,
        bearer_token: str | None = None,
        *,
        timeout: float = 30.0,
        max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
        opener: Callable[..., Any] | None = None,
        bearer_token_provider: Callable[[bool], str | None] | None = None,
        accept_language: str = "en",
        retry_unauthorized: int = 0,
        log_http: bool = True,
        log_raw_http: bool = False,
        logger: Any | None = None,
    ) -> None:
        self.base_url = self._validate_base_url(base_url)
        self.bearer_token = self._normalize_token(bearer_token, "bearer_token")
        self._bearer_token_provider = bearer_token_provider
        self._token_lock = threading.Lock()
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be a finite number greater than zero")
        self.timeout = float(timeout)
        if (
            isinstance(max_response_bytes, bool)
            or not isinstance(max_response_bytes, int)
            or max_response_bytes <= 0
        ):
            raise ValueError("max_response_bytes must be a positive integer")
        self.max_response_bytes = max_response_bytes
        self._opener = opener or urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        ).open
        self.accept_language = self._validate_locale(accept_language)
        if isinstance(retry_unauthorized, bool) or not isinstance(retry_unauthorized, int) or retry_unauthorized < 0:
            raise ValueError("retry_unauthorized must be a non-negative integer")
        self.retry_unauthorized = retry_unauthorized
        self.log_http = bool(log_http)
        self.log_raw_http = bool(log_raw_http)
        if logger is not None and not callable(getattr(logger, "info", None)):
            raise TypeError("logger must provide an info method")
        self.logger = _LOGGER if logger is None else logger
        self.last_response_body: bytes | None = None

    def with_bearer_token(self, token: str) -> "HttpTransport":
        return HttpTransport(
            self.base_url,
            self._normalize_token(token, "bearer_token"),
            timeout=self.timeout,
            max_response_bytes=self.max_response_bytes,
            opener=self._opener,
            accept_language=self.accept_language,
            retry_unauthorized=self.retry_unauthorized,
            log_http=self.log_http,
            log_raw_http=self.log_raw_http,
            logger=self.logger,
        )

    def post(
        self,
        path: str,
        body: Any = _MISSING,
        *,
        headers: dict[str, str] | None = None,
        authorized: bool = True,
        decoder: Callable[[Any], Any] | None = None,
    ) -> Any:
        request_body = None if body is _MISSING else serialize_json(body)
        return self.post_serialized(
            path,
            request_body,
            headers=headers,
            authorized=authorized,
            decoder=decoder,
        )

    def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        authorized: bool = True,
        decoder: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Send an authorized or public GET request and decode its response envelope."""

        return self._request_serialized(
            "GET",
            path,
            None,
            headers=headers,
            authorized=authorized,
            decoder=decoder,
        )

    def post_serialized(
        self,
        path: str,
        body: bytes | None,
        *,
        headers: dict[str, str] | None = None,
        authorized: bool = True,
        decoder: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Send exact JSON bytes, preserving them for signing and transmission."""

        return self._request_serialized(
            "POST",
            path,
            body,
            headers=headers,
            authorized=authorized,
            decoder=decoder,
        )

    def _request_serialized(
        self,
        method: str,
        path: str,
        body: bytes | None,
        *,
        headers: dict[str, str] | None = None,
        authorized: bool = True,
        decoder: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Send one HTTP request using the shared response and retry handling."""

        self.last_response_body = None
        if method not in {"GET", "POST"}:
            raise ValueError("method must be GET or POST")
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise ValueError("path must start with exactly one '/'")
        if any(character in path for character in ("?", "#", "\\")):
            raise ValueError("path must not contain a query, fragment, or backslash")
        if body is not None and not isinstance(body, bytes):
            raise TypeError("body must be bytes or None")
        if headers is not None and not isinstance(headers, dict):
            raise TypeError("headers must be a dictionary")
        if headers is not None:
            for name, value in headers.items():
                if not isinstance(name, str) or not isinstance(value, str):
                    raise TypeError("headers must contain string names and values")
                if (
                    not name.strip()
                    or name != name.strip()
                    or any(char not in _HTTP_HEADER_NAME_CHARS for char in name)
                ):
                    raise ValueError("headers must contain valid HTTP header names")
                if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
                    raise ValueError("headers must not contain control characters")
        if authorized and any(name.lower() == "authorization" for name in (headers or {})):
            raise ValueError("Authorization header is managed by the transport")
        request_headers = {"Accept": "application/json", "Accept-Language": self.accept_language, "User-Agent": _DEFAULT_USER_AGENT}
        request_headers.update(headers or {})
        if authorized:
            request_headers["Authorization"] = f"Bearer {self._current_bearer_token()}"
        if body is not None:
            request_headers.setdefault("Content-Type", "application/json")
        request_url = self.base_url + path
        request = urllib.request.Request(
            request_url,
            data=body,
            headers=request_headers,
            method=method,
        )
        if self.log_http:
            self._log_request(request_url, request_headers, body, method=method)
        response = None
        attempt = 0
        while True:
            try:
                response = self._opener(request, timeout=self.timeout)
                status_value = getattr(response, "status", None)
                status = int(status_value if status_value is not None else response.getcode())
                raw_response = self._read_response(response, status)
                self.last_response_body = raw_response
                if self.log_raw_http:
                    self._log_raw_response(request_url, status, raw_response)
                if self.log_http:
                    self._log_response(request_url, status, raw_response)
                text = self._response_text(raw_response)
                if status != 200:
                    raise LuminalApiException(
                        f"Luminal API returned HTTP {status}",
                        http_status=status,
                        response_body=text,
                    )
                try:
                    envelope = json.loads(raw_response.decode("utf-8"), parse_float=Decimal)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise LuminalApiException(
                        "Luminal API returned invalid JSON",
                        http_status=status,
                        response_body=text,
                        cause=exc,
                    ) from exc
                if not isinstance(envelope, dict) or not isinstance(envelope.get("code"), int) or isinstance(envelope.get("code"), bool):
                    raise LuminalApiException(
                        "Luminal API response is missing an integer code",
                        http_status=status,
                        response_body=text,
                    )
                code = envelope["code"]
                if code != 0:
                    message = envelope.get("msg") or f"Luminal API returned business code {code}"
                    raise LuminalApiException(
                        str(message),
                        http_status=401 if code == 401 else status,
                        api_code=code,
                        response_body=text,
                    )
                data = envelope.get("data")
                if decoder is None:
                    return data
                try:
                    return decoder(data)
                except LuminalApiException:
                    raise
                except Exception as exc:
                    if not self.log_raw_http:
                        self._log_raw_response(request_url, status, raw_response)
                    raise LuminalApiException(
                        "Luminal API response could not be decoded",
                        http_status=status,
                        response_body=text,
                        cause=exc,
                    ) from exc
            except urllib.error.HTTPError as exc:
                try:
                    raw_response = self._read_response(exc, exc.code)
                    self.last_response_body = raw_response
                finally:
                    self._close_response(exc)
                if self.log_raw_http:
                    self._log_raw_response(request_url, exc.code, raw_response)
                if self.log_http:
                    self._log_response(request_url, exc.code, raw_response)
                text = self._response_text(raw_response)
                error = LuminalApiException(
                    f"Luminal API returned HTTP {exc.code}",
                    http_status=exc.code,
                    response_body=text,
                    cause=exc,
                )
                if self._can_retry_unauthorized(authorized, attempt, error):
                    attempt += 1
                    request.headers["Authorization"] = f"Bearer {self._refresh_bearer_token()}"
                    continue
                raise error from exc
            except LuminalApiException as exc:
                if self._can_retry_unauthorized(authorized, attempt, exc):
                    attempt += 1
                    request.headers["Authorization"] = f"Bearer {self._refresh_bearer_token()}"
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise LuminalApiException("Luminal API request failed", cause=exc) from exc
            except Exception as exc:
                raise LuminalApiException("Luminal API request failed", cause=exc) from exc
            finally:
                self._close_response(response)

    def _log_request(
        self,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        *,
        method: str = "POST",
    ) -> None:
        if not self._logging_enabled():
            return
        safe_headers = {
            name: "<redacted>" if name.lower() in _SENSITIVE_LOG_HEADERS else value
            for name, value in headers.items()
        }
        self.logger.info(
            "HTTP request method={} url={} headers={} body={}".format(
                method,
                json.dumps(url, ensure_ascii=False),
                json.dumps(safe_headers, ensure_ascii=False, separators=(",", ":")),
                json.dumps(self._redact_log_body(body), ensure_ascii=False),
            )
        )

    def _log_webhook(self, event: str, event_id: str, body: bytes) -> None:
        if not self._logging_enabled():
            return
        self.logger.info(
            "WEBHOOK event={} eventId={} body={}".format(
                event, event_id, self._redact_log_body(body)
            )
        )

    def _log_response(self, url: str, status: int, body: bytes) -> None:
        if not self._logging_enabled():
            return
        self.logger.info(
            "HTTP response url={} status={} body={}".format(
                json.dumps(url, ensure_ascii=False),
                status,
                json.dumps(self._redact_log_body(body), ensure_ascii=False),
            )
        )

    def _log_raw_response(self, url: str, status: int, body: bytes) -> None:
        if not self.log_http or not self._logging_enabled():
            return
        self.logger.info(
            "HTTP raw response url={} status={} body={}".format(
                json.dumps(url, ensure_ascii=False),
                status,
                json.dumps(body.decode("utf-8", errors="replace"), ensure_ascii=False),
            )
        )

    @classmethod
    def _redact_log_body(cls, body: bytes | None) -> str:
        if not body:
            return ""
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return f"<non-json {len(body)} bytes>"
        return json.dumps(cls._redact_log_value(value), ensure_ascii=False, separators=(",", ":"))

    def _logging_enabled(self) -> bool:
        if not self.log_http:
            return False
        is_enabled_for = getattr(self.logger, "isEnabledFor", None)
        return bool(is_enabled_for(logging.INFO)) if callable(is_enabled_for) else True

    @classmethod
    def _redact_log_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "<redacted>" if key.lower() in _SENSITIVE_LOG_BODY_KEYS else cls._redact_log_value(child)
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [cls._redact_log_value(child) for child in value]
        return value

    def _refresh_bearer_token(self) -> str:
        if self._bearer_token_provider is None:
            raise LuminalApiException("bearer_token must not be blank")
        with self._token_lock:
            token = self._bearer_token_provider(True)
            token = self._normalize_token(token, "bearer_token")
            if token is None:
                raise LuminalApiException("bearer_token must not be blank")
            self.bearer_token = token
            return token

    def _current_bearer_token(self) -> str:
        if self._bearer_token_provider is None:
            token = self._normalize_token(self.bearer_token, "bearer_token")
            if token is None:
                raise ValueError("bearer_token must not be blank")
            return token
        with self._token_lock:
            token = self._bearer_token_provider(False)
            token = self._normalize_token(token, "bearer_token")
            if token is None:
                raise ValueError("bearer_token must not be blank")
            self.bearer_token = token
            return token

    @staticmethod
    def _should_retry_unauthorized(exc: LuminalApiException) -> bool:
        text = (exc.response_body or str(exc)).lower()
        return exc.http_status == 401 or exc.api_code == 401 or "not logged in" in text or "unauthorized" in text

    def _can_retry_unauthorized(self, authorized: bool, attempt: int, exc: LuminalApiException) -> bool:
        return (
            authorized
            and self._bearer_token_provider is not None
            and attempt < self.retry_unauthorized
            and self._should_retry_unauthorized(exc)
        )

    @staticmethod
    def _validate_locale(value: str) -> str:
        if value not in {"en", "zh"}:
            raise ValueError("accept_language must be 'en' or 'zh'")
        return value

    @staticmethod
    def _response_text(raw_response: bytes) -> str:
        if len(raw_response) <= _MAX_ERROR_BODY_BYTES:
            return raw_response.decode("utf-8", errors="replace")
        return (
            raw_response[:_MAX_ERROR_BODY_BYTES].decode("utf-8", errors="replace")
            + _ERROR_BODY_TRUNCATION_MARKER
        )

    def _read_response(self, response: Any, status: int) -> bytes:
        raw_response = response.read(self.max_response_bytes + 1)
        if not isinstance(raw_response, bytes):
            raise TypeError("HTTP response body must be bytes")
        if len(raw_response) > self.max_response_bytes:
            raise LuminalApiException(
                "Luminal API response exceeded max_response_bytes",
                http_status=status,
            )
        return raw_response

    @staticmethod
    def _close_response(response: Any) -> None:
        if response is None:
            return
        close = getattr(response, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

    @staticmethod
    def _normalize_token(token: str | None, name: str) -> str | None:
        if token is None:
            return None
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"{name} must not be blank")
        return token

    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("base_url must not be blank")
        if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in value):
            raise ValueError("base_url must not contain whitespace or control characters")
        try:
            parsed = urllib.parse.urlparse(value.rstrip("/"))
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("base_url must be an absolute HTTP or HTTPS URL") from exc
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            raise ValueError("base_url must be an absolute HTTP or HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain credentials")
        if port is not None and not 1 <= port <= 65_535:
            raise ValueError("base_url must contain a valid port")
        if parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain a query string or fragment")
        return value.rstrip("/")


def require_non_blank(value: str, name: str) -> str:
    """Validate a required non-blank string argument."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value
