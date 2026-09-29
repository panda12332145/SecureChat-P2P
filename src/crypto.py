"""Criptografia do SecureChat-P2P.

Chave derivada via PBKDF2-SHA256 (100k iterações) a partir de uma senha
pré-compartilhada. O salt é fixo e PÚBLICO de propósito: os dois lados
precisam derivar exatamente a mesma chave (padrão PSK), ao contrário de
um salt aleatório por processo, que geraria chaves diferentes em cada
ponta e tornaria a troca impossível.
"""
import os
from base64 import b64encode, b64decode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

BUFFER_SIZE = 4096
DEFAULT_SALT = b"SecureChatP2P-v1"
KDF_ITERATIONS = 100_000
IV_SIZE = 16


def derive_key(password: str, salt: bytes = DEFAULT_SALT) -> bytes:
    """Deriva uma chave AES-256 (32 bytes) da senha compartilhada."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode())


def encrypt_bytes(data: bytes, key: bytes) -> str:
    """Cifra bytes com AES-256-CFB8. Retorna base64(iv + texto cifrado)."""
    iv = os.urandom(IV_SIZE)
    enc = Cipher(algorithms.AES(key), modes.CFB(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    return b64encode(iv + ct).decode("ascii")


def decrypt_bytes(payload_b64: str, key: bytes) -> bytes:
    """Decifra o retorno de encrypt_bytes. Lança ValueError se a chave errar."""
    raw = b64decode(payload_b64)
    iv, ct = raw[:IV_SIZE], raw[IV_SIZE:]
    dec = Cipher(algorithms.AES(key), modes.CFB(iv)).decryptor()
    return dec.update(ct) + dec.finalize()


def encrypt_message(message: str, key: bytes) -> str:
    return encrypt_bytes(message.encode("utf-8"), key)


def decrypt_message(ciphertext_b64: str, key: bytes) -> str:
    return decrypt_bytes(ciphertext_b64, key).decode("utf-8")


def encrypt_file(file_path: str, key: bytes) -> str:
    with open(file_path, "rb") as f:
        return encrypt_bytes(f.read(), key)


def decrypt_to_file(payload_b64: str, key: bytes, out_path: str) -> int:
    data = decrypt_bytes(payload_b64, key)
    with open(out_path, "wb") as f:
        f.write(data)
    return len(data)
