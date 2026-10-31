"""scrypt password hashing; encoded parameters are fixed for this schema version."""
import base64
import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split('$')
        if algorithm != 'scrypt':
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False
