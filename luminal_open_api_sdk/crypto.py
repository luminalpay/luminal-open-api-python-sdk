"""Dependency-free RSA SHA256withRSA helpers used by the SDK."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any

_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True, slots=True)
class RsaPrivateKey:
    """Minimal PKCS#8 RSA private-key representation."""

    modulus: int
    private_exponent: int

    def __repr__(self) -> str:
        return "RsaPrivateKey(<redacted>)"


@dataclass(frozen=True, slots=True)
class RsaPublicKey:
    """Minimal X.509 RSA public-key representation."""

    modulus: int
    public_exponent: int


def _read_length(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("DER length is missing")
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    size = first & 0x7F
    if size == 0 or offset + size > len(data) or data[offset] == 0:
        raise ValueError("DER length is invalid")
    length = int.from_bytes(data[offset : offset + size], "big")
    if length < 0x80:
        raise ValueError("DER length is not minimally encoded")
    return length, offset + size


def _read_tlv(data: bytes, offset: int = 0) -> tuple[int, bytes, int]:
    if offset >= len(data):
        raise ValueError("DER value is missing")
    tag = data[offset]
    length, value_offset = _read_length(data, offset + 1)
    end = value_offset + length
    if end > len(data):
        raise ValueError("DER value is truncated")
    return tag, data[value_offset:end], end


def _read_integer(value: bytes) -> int:
    if not value:
        raise ValueError("DER integer is empty")
    if value[0] & 0x80 or (len(value) > 1 and value[0] == 0 and not value[1] & 0x80):
        raise ValueError("DER integer must be minimally encoded and non-negative")
    return int.from_bytes(value, "big", signed=False)


def _validate_rsa_modulus(modulus: int) -> None:
    if modulus < 2 or modulus % 2 == 0:
        raise ValueError("RSA modulus must be a positive odd integer")


def _validate_rsa_public_exponent(exponent: int) -> None:
    if exponent <= 1 or exponent % 2 == 0:
        raise ValueError("RSA public exponent must be an odd integer greater than one")


def _validate_rsa_private_key(key: RsaPrivateKey) -> None:
    _validate_rsa_modulus(key.modulus)
    if key.private_exponent <= 0:
        raise ValueError("RSA private exponent must be positive")


def _validate_rsa_algorithm(items: list[tuple[int, bytes]]) -> None:
    if len(items) < 2 or items[0][0] != 0x06 or items[0][1] != bytes.fromhex("2a864886f70d010101"):
        raise ValueError("RSA algorithm identifier is invalid")
    if items[1][0] != 0x05 or items[1][1] != b"":
        raise ValueError("RSA algorithm parameters are invalid")


def _sequence_items(data: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        tag, value, offset = _read_tlv(data, offset)
        items.append((tag, value))
    return items


def _decode_pem(pem: str, begin: str, end: str) -> bytes:
    if not isinstance(pem, str) or begin not in pem or end not in pem:
        raise ValueError("PEM header or footer is missing")
    body = pem.split(begin, 1)[1].split(end, 1)[0]
    body = re.sub(r"\s+", "", body)
    try:
        return base64.b64decode(body, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("PEM body is not valid Base64") from exc


def read_public_key(pem: str) -> RsaPublicKey:
    """Read an X.509 ``PUBLIC KEY`` PEM or PKCS#1 ``RSA PUBLIC KEY`` PEM."""

    try:
        if "-----BEGIN PUBLIC KEY-----" in pem:
            der = _decode_pem(pem, "-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----")
            tag, outer, end = _read_tlv(der)
            if tag != 0x30 or end != len(der):
                raise ValueError("SubjectPublicKeyInfo must be a DER sequence")
            items = _sequence_items(outer)
            if len(items) != 2 or items[0][0] != 0x30:
                raise ValueError("SubjectPublicKeyInfo is invalid")
            _validate_rsa_algorithm(_sequence_items(items[0][1]))
            bit_string = items[1][1]
            if items[1][0] != 0x03 or not bit_string or bit_string[0] != 0:
                raise ValueError("SubjectPublicKeyInfo bit string is invalid")
            tag, rsa_body, end = _read_tlv(bit_string[1:])
            if tag != 0x30 or end != len(bit_string) - 1:
                raise ValueError("RSA public key is invalid")
            rsa_items = _sequence_items(rsa_body)
        elif "-----BEGIN RSA PUBLIC KEY-----" in pem:
            der = _decode_pem(pem, "-----BEGIN RSA PUBLIC KEY-----", "-----END RSA PUBLIC KEY-----")
            tag, body, end = _read_tlv(der)
            if tag != 0x30 or end != len(der):
                raise ValueError("RSA public key must be a DER sequence")
            rsa_items = _sequence_items(body)
        else:
            raise ValueError("Unsupported RSA public-key PEM header")
        if len(rsa_items) != 2 or rsa_items[0][0] != 0x02 or rsa_items[1][0] != 0x02:
            raise ValueError("RSA public key integers are missing")
        modulus = _read_integer(rsa_items[0][1])
        exponent = _read_integer(rsa_items[1][1])
        _validate_rsa_modulus(modulus)
        _validate_rsa_public_exponent(exponent)
        return RsaPublicKey(modulus, exponent)
    except (IndexError, ValueError, TypeError) as exc:
        raise ValueError("Invalid X.509 RSA public key PEM") from exc


def read_private_key(pem: str) -> RsaPrivateKey:
    """Read a PKCS#8 ``PRIVATE KEY`` PEM or PKCS#1 ``RSA PRIVATE KEY`` PEM."""

    try:
        if "-----BEGIN PRIVATE KEY-----" in pem:
            der = _decode_pem(pem, "-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----")
            tag, outer, end = _read_tlv(der)
            if tag != 0x30 or end != len(der):
                raise ValueError("PrivateKeyInfo must be a DER sequence")
            items = _sequence_items(outer)
            if (
                len(items) != 3
                or items[0][0] != 0x02
                or _read_integer(items[0][1]) != 0
                or items[1][0] != 0x30
                or items[2][0] != 0x04
            ):
                raise ValueError("PKCS#8 private key structure is invalid")
            _validate_rsa_algorithm(_sequence_items(items[1][1]))
            tag, rsa_body, end = _read_tlv(items[2][1])
            if tag != 0x30 or end != len(items[2][1]):
                raise ValueError("RSA private key is invalid")
            rsa_items = _sequence_items(rsa_body)
        elif "-----BEGIN RSA PRIVATE KEY-----" in pem:
            der = _decode_pem(pem, "-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----")
            tag, body, end = _read_tlv(der)
            if tag != 0x30 or end != len(der):
                raise ValueError("RSA private key must be a DER sequence")
            rsa_items = _sequence_items(body)
        else:
            raise ValueError("Unsupported RSA private-key PEM header")
        if len(rsa_items) < 4 or any(tag != 0x02 for tag, _ in rsa_items[:4]):
            raise ValueError("RSA private key integers are missing")
        if _read_integer(rsa_items[0][1]) != 0:
            raise ValueError("Only two-prime RSA private keys are supported")
        key = RsaPrivateKey(_read_integer(rsa_items[1][1]), _read_integer(rsa_items[3][1]))
        _validate_rsa_private_key(key)
        return key
    except (IndexError, ValueError, TypeError) as exc:
        raise ValueError("Invalid PKCS#8 RSA private key PEM") from exc


def sign(content: bytes, private_key: RsaPrivateKey) -> str:
    """Sign exact bytes with SHA256withRSA and return a Base64 signature."""

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if not isinstance(private_key, RsaPrivateKey):
        raise TypeError("private_key must be RsaPrivateKey")
    _validate_rsa_private_key(private_key)
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(content).digest()
    size = (private_key.modulus.bit_length() + 7) // 8
    padding_size = size - len(digest_info) - 3
    if padding_size < 8:
        raise ValueError("RSA modulus is too short for SHA256withRSA")
    encoded = b"\x00\x01" + b"\xff" * padding_size + b"\x00" + digest_info
    encoded_value = int.from_bytes(encoded, "big")
    if encoded_value >= private_key.modulus:
        raise ValueError("RSA modulus is too small for the encoded signature")
    signature = pow(encoded_value, private_key.private_exponent, private_key.modulus)
    return base64.b64encode(signature.to_bytes(size, "big")).decode("ascii")


def verify(content: bytes, signature: str, public_key: RsaPublicKey) -> bool:
    """Verify a Base64 SHA256withRSA signature against exact bytes."""

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if not isinstance(public_key, RsaPublicKey):
        raise TypeError("public_key must be RsaPublicKey")
    try:
        _validate_rsa_modulus(public_key.modulus)
        _validate_rsa_public_exponent(public_key.public_exponent)
    except ValueError:
        return False
    if not isinstance(signature, str) or not signature.strip():
        return False
    try:
        raw_signature = base64.b64decode(signature, validate=True)
        size = (public_key.modulus.bit_length() + 7) // 8
        if len(raw_signature) != size:
            return False
        padding_size = size - len(_SHA256_DIGEST_INFO_PREFIX) - 32 - 3
        if padding_size < 8:
            return False
        signature_value = int.from_bytes(raw_signature, "big")
        if signature_value >= public_key.modulus:
            return False
        encoded = pow(signature_value, public_key.public_exponent, public_key.modulus)
        expected = b"\x00\x01" + b"\xff" * padding_size + b"\x00"
        expected += _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(content).digest()
        return hmac.compare_digest(encoded.to_bytes(size, "big"), expected)
    except (ValueError, TypeError, OverflowError):
        return False


def sign_canonical_json(value: Any, private_key: RsaPrivateKey) -> str:
    """Sign a value after canonical SDK JSON serialization."""

    from .transport import serialize_json_for_signature

    return sign(serialize_json_for_signature(value), private_key)


class RsaSignatures:
    """Java-style facade for RSA helper functions."""

    sign = staticmethod(sign)
    verify = staticmethod(verify)
    sign_canonical_json = staticmethod(sign_canonical_json)
    read_private_key = staticmethod(read_private_key)
    read_public_key = staticmethod(read_public_key)
