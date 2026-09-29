"""Camada de rede do SecureChat-P2P.

Protocolo de linha (delimitado por \\n), imune a fragmentação do TCP:

  mensagem : <base64 do texto cifrado>\\n
  arquivo  : FILE:<tamanho>:<nome>\\n<tamanho bytes de base64 cifrado>

O base64 nunca contém \\n, então o delimitador é seguro. O tamanho no
cabeçalho do arquivo elimina a ambiguidade de "até quando ler" que
travava transferências múltiplas do buffer.
"""
import os
import socket
import threading
from typing import Callable, Optional

from .crypto import (
    BUFFER_SIZE,
    decrypt_bytes,
    encrypt_bytes,
    encrypt_message,
    decrypt_message,
)

MessageCb = Optional[Callable[[str], None]]
FileCb = Optional[Callable[[str, str], None]]


def _recv_line(sock: socket.socket, buf: bytearray) -> bytes:
    while True:
        idx = buf.find(b"\n")
        if idx >= 0:
            line = bytes(buf[:idx])
            del buf[: idx + 1]
            return line
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            raise ConnectionError("Conexão encerrada pelo peer.")
        buf += chunk


def _recv_exact(sock: socket.socket, buf: bytearray, n: int) -> bytes:
    while len(buf) < n:
        chunk = sock.recv(BUFFER_SIZE)
        if not chunk:
            raise ConnectionError("Conexão encerrada no meio do arquivo.")
        buf += chunk
    out = bytes(buf[:n])
    del buf[:n]
    return out


def send_msg(sock: socket.socket, message: str, key: bytes) -> None:
    """Envia uma mensagem de texto cifrada."""
    sock.sendall(encrypt_message(message, key).encode("ascii") + b"\n")


def send_file(sock: socket.socket, file_path: str, key: bytes) -> str:
    """Envia um arquivo cifrado. Retorna o nome base enviado."""
    name = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        payload = encrypt_bytes(f.read(), key).encode("ascii")
    header = f"FILE:{len(payload)}:{name}\n".encode("utf-8")
    sock.sendall(header + payload)
    return name


def handle_peer(sock: socket.socket, key: bytes,
                on_message: MessageCb = None, on_file: FileCb = None,
                save_dir: Optional[str] = None) -> None:
    """Loop de recepção de um peer conectado."""
    save_dir = save_dir or os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs(save_dir, exist_ok=True)
    buf = bytearray()
    while True:
        line = _recv_line(sock, buf)
        if line.startswith(b"FILE:"):
            try:
                _, len_s, name = line.decode("utf-8").split(":", 2)
                length = int(len_s)
            except ValueError:
                continue
            payload = _recv_exact(sock, buf, length).decode("ascii")
            data = decrypt_bytes(payload, key)
            # basename: protege contra path traversal no nome recebido
            safe_name = os.path.basename(name) or "arquivo_recebido.bin"
            out_path = os.path.join(save_dir, safe_name)
            with open(out_path, "wb") as f:
                f.write(data)
            if on_file:
                on_file(safe_name, out_path)
        else:
            msg = decrypt_message(line.decode("ascii"), key)
            if on_message:
                on_message(msg)


def _safe_handle(sock, key, on_message=None, on_file=None, save_dir=None):
    """handle_peer com captura de desconexão (evita traceback em thread)."""
    try:
        handle_peer(sock, key, on_message, on_file, save_dir)
    except (ConnectionError, OSError):
        try:
            sock.close()
        except OSError:
            pass


def listen_for_peers(server: socket.socket, key: bytes,
                     on_message: MessageCb = None, on_file: FileCb = None,
                     save_dir: Optional[str] = None) -> None:
    """Aceita conexões de entrada em loop (roda numa thread)."""
    while True:
        try:
            client, _addr = server.accept()
        except OSError:
            break
        threading.Thread(
            target=_safe_handle,
            args=(client, key, on_message, on_file, save_dir),
            daemon=True,
        ).start()


def start_server(port: int) -> socket.socket:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    return srv


def connect_to_peer(host: str, port: int, retries: int = 3,
                    delay: float = 1.0) -> socket.socket:
    import time
    last_err: Exception = OSError("sem tentativa")
    for i in range(retries):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((host, port))
            return s
        except OSError as e:
            last_err = e
            time.sleep(delay)
    raise ConnectionError(
        f"Não foi possível conectar a {host}:{port} — {last_err}"
    )
