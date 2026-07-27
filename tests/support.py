"""Shared test helpers for the standalone SDK test suite."""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from typing import Any

from luminal_open_api_sdk import LuminalOpenApiClient

PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MIICdQIBADANBgkqhkiG9w0BAQEFAASCAl8wggJbAgEAAoGBAKx39N2msMQNaTp9
Yr+AHwA5Jb0p+mBUkNhIxUJuyLg3cn5ywI/Zw68w27muV0VgI/RZEoOrjHkPm189
9HvvpwBBZGXVNElWMkd4aQVQ1FuEqVzv1TprzEexYicn7OkAdVPbNuUQZ6FKDcNz
X0miZ2NFph30y+YiVVBx8luCFIXXAgMBAAECgYAYPLtistxAkQnquFg6RU0WAPH2
xYF0LC421vMxxNPcX55ter7o+FdxtVILpB6Ll1k2K5ZYfrE9Ch5xoglLqYA0Y+w2
/xBqRYHT3vGb+fkS9S19OfBW3tVH7j2F/kygDQMKAqGgEd40ZN8NCDbRXtWv1tG+
1EHKeiD+yjPf0jYM8QJBANR2UBGN9H1vXH/zr0YoyZ2QldLiE72cAjM5XwdWniRJ
SpkgaPIDOjwh36RjPAswwRSK/HDBauch0p1dOQK3ZDMCQQDPz5hei3GIwxoXRUd8
/kO71YAjaRgjbWaxw3yxuE4J8wa1yM290lsSftJRS7pEr5UdGsBlnXIPk4dNpJau
kJPNAkBVGVaU0XEeVN6N+YM47NlknScForwZdEWFUvN3MwCAtEKG9u5SEWzf7Qlx
BLZmHQ8ZNVpLp400Kt37Xf2Z0u71AkAUbHm0KQ5Ce7JPwS5SeYbcqhIK6ORHbxQd
unHB4bRBxBHPwel+k3MB8VboSIIJCBymnJ92HTA9mak9l0R76ZetAkA2CSjh0P3W
aivhUu5xkWJmYD51t3L15L4xSGdl+jagWgHW4Yh7kr+SSYAXJjX1qp/MOkaVYw7G
XxA5QsFZwTMa
-----END PRIVATE KEY-----
"""

PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCsd/TdprDEDWk6fWK/gB8AOSW9
KfpgVJDYSMVCbsi4N3J+csCP2cOvMNu5rldFYCP0WRKDq4x5D5tfPfR776cAQWRl
1TRJVjJHeGkFUNRbhKlc79U6a8xHsWInJ+zpAHVT2zblEGehSg3Dc19JomdjRaYd
9MvmIlVQcfJbghSF1wIDAQAB
-----END PUBLIC KEY-----
"""

SANDBOX_WEBHOOK_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxD4ii20YBI2JwPIfXaXy
PHA1aL1p545F9zvQRPUXvvepkkgI4Pxh1eS4qTx17OVstFGamh5mjeI+3Lu2du7
DNIwM1p2Dl12OkEH2RtGi4H4jcRf9wNJCXCMt6b3bwEW3osYqW8HDusDMYYjBvA
aWw9Vv2/uvVNDz39ntVca7T54Hjml5tsP/fpYERO3vvB9yAlmfIISOD5Ggf335i
dL6m/ALAs1bAdiGxKIoHb6sMb76Iw18clbDlLDaPqyeUXNR9YKZuZvts+AOlp9f
IMSJAuW8HmSm03fxBMyfKPsFu8AoeS74yM1QdEkOrgFB+dNoREyV0p0YXPZ3vDl
dZnUIXQIDAQAB
-----END PUBLIC KEY-----"""


@dataclass
class FakeResponse:
    body: bytes
    status: int = 200
    closed: bool = False

    def read(self, size: int | None = None) -> bytes:
        return self.body if size is None else self.body[:size]

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.request = None

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        self.request = request
        return self.response


class SequenceOpener:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        self.requests.append(request)
        return self.responses.pop(0)


def client_for(data: Any, *, token: str = "access-token") -> tuple[LuminalOpenApiClient, FakeOpener]:
    response = FakeResponse(json.dumps({"code": 0, "msg": "success", "data": data}).encode())
    opener = FakeOpener(response)
    return LuminalOpenApiClient("https://api.example.test", token, opener=opener), opener


def body_text(opener: FakeOpener) -> str:
    assert opener.request is not None
    return (opener.request.data or b"").decode("utf-8")


def request_path(opener: FakeOpener) -> str:
    assert opener.request is not None
    return opener.request.full_url.removeprefix("https://api.example.test")


def request_header(opener: FakeOpener, name: str) -> str | None:
    assert opener.request is not None
    wanted = name.lower()
    return next(
        (value for key, value in opener.request.header_items() if key.lower() == wanted),
        None,
    )


def assert_request_contract(
    test: unittest.TestCase,
    opener: FakeOpener,
    path: str,
    body: str,
    *,
    authorization: str = "Bearer access-token",
    signature: str | None = None,
) -> None:
    assert opener.request is not None
    test.assertEqual("POST", opener.request.get_method())
    test.assertEqual(path, request_path(opener))
    test.assertEqual("application/json", request_header(opener, "Accept"))
    test.assertEqual("en", request_header(opener, "Accept-Language"))
    test.assertEqual(authorization, request_header(opener, "Authorization"))
    test.assertEqual("application/json" if body else None, request_header(opener, "Content-Type"))
    test.assertEqual(signature, request_header(opener, "sign"))
    test.assertEqual(body, body_text(opener))
