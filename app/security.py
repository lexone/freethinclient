"""Password storage and strict version parsing, without external dependencies."""
import hashlib
import hmac
import re
import secrets


def password_hash(password):
    if len(password) < 12:
        raise ValueError("Use uma senha com pelo menos 12 caracteres.")
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def password_ok(password, stored):
    try:
        method, salt, digest = stored.split("$")
        if method != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise ValueError("Versão inválida: esperado X.Y.Z estável.")
    return tuple(map(int, value.split(".")))
