"""Authentication tests use synthetic hashes and never read local credentials."""

import hashlib

import pytest

from brunus_mes.auth import verify_password


def make_hash(password="palavra de teste", iterations=1_000):
    salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest}"


def test_correct_password_and_wrong_password():
    stored = make_hash()
    assert verify_password("palavra de teste", stored)
    assert not verify_password("outra palavra", stored)


def test_compatible_with_credential_generator():
    assert verify_password("Demonstração çã!", make_hash("Demonstração çã!", 600_000))


@pytest.mark.parametrize(
    "stored",
    [
        None,
        123,
        "",
        "pbkdf2_sha256$1000$00",
        "pbkdf2_sha256$1000$00$" + "a" * 64 + "$extra",
        "sha256$1000$00$" + "a" * 64,
        "pbkdf2_sha256$0$00$" + "a" * 64,
        "pbkdf2_sha256$-1$00$" + "a" * 64,
        "pbkdf2_sha256$abc$00$" + "a" * 64,
        "pbkdf2_sha256$10000001$00$" + "a" * 64,
        "pbkdf2_sha256$9999999999999999999999$00$" + "a" * 64,
        "pbkdf2_sha256$ 1000$00$" + "a" * 64,
        "pbkdf2_sha256$1000$$" + "a" * 64,
        "pbkdf2_sha256$1000$0$" + "a" * 64,
        "pbkdf2_sha256$1000$gg$" + "a" * 64,
        "pbkdf2_sha256$1000$00 11$" + "a" * 64,
        "pbkdf2_sha256$1000$" + "00" * 65 + "$" + "a" * 64,
        "pbkdf2_sha256$1000$00$" + "a" * 63,
        "pbkdf2_sha256$1000$00$" + "z" * 64,
    ],
)
def test_invalid_hash_fails_closed(stored):
    assert not verify_password("palavra de teste", stored)


@pytest.mark.parametrize("password", [None, 123, b"palavra de teste", "\ud800"])
def test_invalid_password_input_fails_closed(password):
    assert not verify_password(password, make_hash())
