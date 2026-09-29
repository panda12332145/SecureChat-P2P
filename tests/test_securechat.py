"""Testes do SecureChat-P2P (sem interface gráfica)."""
import os
import socket
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.crypto import (
    DEFAULT_SALT,
    decrypt_bytes,
    decrypt_message,
    derive_key,
    encrypt_bytes,
    encrypt_message,
)
from src import network


def test_same_password_same_key():
    """Os dois lados com a mesma senha DEVEM derivar a mesma chave."""
    k1 = derive_key("senha-secreta")
    k2 = derive_key("senha-secreta", DEFAULT_SALT)
    assert k1 == k2, "chaves diferentes = chat impossível"
    assert len(k1) == 32
    assert derive_key("outra") != k1


def test_message_roundtrip():
    key = derive_key("abc123")
    ct = encrypt_message("Olá, mundo! 🐼", key)
    assert decrypt_message(ct, key) == "Olá, mundo! 🐼"
    try:
        decrypt_message(ct, derive_key("errada"))
        raise AssertionError("chave errada deveria falhar")
    except Exception:
        pass


def test_file_roundtrip_exact_buffer_size():
    """Arquivo com tamanho múltiplo exato do buffer (bug antigo travava aqui)."""
    key = derive_key("abc123")
    data = os.urandom(network.BUFFER_SIZE * 2)  # 8192 bytes exatos
    tmp_in = "/tmp/sc_in.bin"
    tmp_out = "/tmp/sc_out.bin"
    with open(tmp_in, "wb") as f:
        f.write(data)
    from src.crypto import encrypt_file, decrypt_to_file
    payload = encrypt_file(tmp_in, key)
    decrypt_to_file(payload, key, tmp_out)
    with open(tmp_out, "rb") as f:
        assert f.read() == data


def test_framing_messages_and_file_over_socketpair():
    key = derive_key("par123")
    srv, cli = socket.socketpair()
    received = []
    files = []

    def on_msg(m):
        received.append(m)

    def on_file(name, path):
        files.append((name, path))

    t = threading.Thread(
        target=network.handle_peer,
        args=(srv, key, on_msg, on_file, "/tmp/sc_dl"),
        daemon=True,
    )
    t.start()

    # sequência: 3 mensagens, 1 arquivo, 1 mensagem (fragmentação implícita)
    network.send_msg(cli, "Ana: oi", key)
    network.send_msg(cli, "Ana: segunda", key)
    with open("/tmp/sc_send.bin", "wb") as f:
        f.write(os.urandom(12345))
    network.send_file(cli, "/tmp/sc_send.bin", key)
    network.send_msg(cli, "Ana: depois do arquivo", key)
    cli.shutdown(socket.SHUT_WR)
    t.join(timeout=5)

    assert received == ["Ana: oi", "Ana: segunda", "Ana: depois do arquivo"], received
    assert len(files) == 1
    name, path = files[0]
    assert name == "sc_send.bin"
    with open(path, "rb") as f, open("/tmp/sc_send.bin", "rb") as g:
        assert f.read() == g.read()


def test_path_traversal_blocked():
    """Nome '../../evil' recebido deve ser salvo apenas como basename."""
    key = derive_key("x")
    srv, cli = socket.socketpair()
    files = []
    t = threading.Thread(
        target=network.handle_peer,
        args=(srv, key, None, lambda n, p: files.append((n, p)), "/tmp/sc_dl2"),
        daemon=True,
    )
    t.start()
    payload = encrypt_bytes(b"conteudo", key).encode("ascii")
    cli.sendall(f"FILE:{len(payload)}:../../evil.txt\n".encode() + payload)
    cli.shutdown(socket.SHUT_WR)
    t.join(timeout=5)
    assert files and files[0][0] == "evil.txt"
    assert files[0][1] == "/tmp/sc_dl2/evil.txt"
    assert not os.path.exists("/tmp/evil.txt")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"✅ {fn.__name__}")
    print(f"\n{len(fns)} testes passaram.")
