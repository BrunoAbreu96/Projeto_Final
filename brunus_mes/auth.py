"""Password verification independent of the Streamlit interface."""

import hashlib
import hmac
import re


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify the PBKDF2-SHA256 format produced by gerar_credenciais.py.

    Malformed configuration fails closed. An upper iteration limit prevents a
    corrupt configuration from tying up a worker for an unbounded time.
    """
    if not isinstance(password, str) or not isinstance(stored_hash, str):
        return False
    try:
        algorithm, iterations_text, salt_hex, digest_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        if re.fullmatch(r"[0-9]{1,8}", iterations_text) is None:
            return False
        iterations = int(iterations_text)
        if not 1 <= iterations <= 10_000_000:
            return False
        if (
            re.fullmatch(r"[0-9a-fA-F]{2,128}", salt_hex) is None
            or len(salt_hex) % 2
            or re.fullmatch(r"[0-9a-fA-F]{64}", digest_hex) is None
        ):
            return False
        calculated = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        )
        return hmac.compare_digest(calculated, bytes.fromhex(digest_hex))
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return False
