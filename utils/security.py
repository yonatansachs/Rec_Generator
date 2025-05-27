import hashlib


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()