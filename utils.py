"""Helpers for generating URL-safe short codes."""
import secrets
import string

_ALPHABET = string.ascii_letters + string.digits  # base62


def generate_short_code(length: int = 7) -> str:
    """Cryptographically-random base62 code. With length=7 there are
    62^7 (~3.5 trillion) possible codes - collisions are checked for and
    retried by the caller, so this only needs to be "random enough", not
    guaranteed unique."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
