"""Interface Tkinter (dark) do SecureChat-P2P."""
import os
import socket
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext

from .crypto import derive_key
from .network import (
    connect_to_peer,
    listen_for_peers,
    send_file,
    send_msg,
    start_server,
)

BG = "#1a1a2e"
BG2 = "#16213e"
ACCENT = "#e94560"
ACCENT2 = "#533483"
FG = "#e0e0e0"


class ChatApp(tk.Tk):
    def __init__(self, username: str, key: bytes, listen_port: int):
        super().__init__()
        self.username = username
        self.key = key
        self.listen_port = listen_port
        self.peer_socket: socket.socket | None = None
        self.save_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        self.title(f"SecureChat P2P — {username}")
        self.geometry("760x540")
        self.configure(bg=BG)
        self._build_ui()

        # servidor sempre ativo: o outro lado pode conectar a qualquer momento
        srv = start_server(listen_port)
        threading.Thread(
            target=listen_for_peers,
            args=(srv, key, self.on_message_threadsafe,
                  self.on_file_threadsafe, self.save_dir),
            daemon=True,
        ).start()
        self.append(f"[servidor escutando na porta {listen_port}]")

    # ---------- UI ----------
    def _build_ui(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 0))

        tk.Label(top, text="Peer (host:porta):", bg=BG, fg=FG,
                 font=("Consolas", 10)).pack(side="left")
        self.peer_entry = tk.Entry(top, bg=BG2, fg="white",
                                   insertbackground="white", font=("Consolas", 11))
        self.peer_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=5)
        self.peer_entry.insert(0, f"127.0.0.1:{self.listen_port}")

        tk.Button(top, text="Conectar", command=self.connect_peer,
                  bg=ACCENT, fg="white", activebackground="#c73652",
                  font=("Consolas", 10), bd=0).pack(side="left", ipady=5, ipadx=10)

        self.chat_area = scrolledtext.ScrolledText(
            self, state="disabled", wrap="word", bg=BG2, fg=FG,
            font=("Consolas", 11), bd=0)
        self.chat_area.pack(padx=10, pady=10, fill="both", expand=True)

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        self.entry = tk.Entry(bottom, bg=BG2, fg="white",
                              insertbackground="white", font=("Consolas", 12), bd=0)
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 5))
        self.entry.bind("<Return>", self._send)

        tk.Button(bottom, text="Enviar", command=self._send, bg=ACCENT,
                  fg="white", font=("Consolas", 11), bd=0,
                  activebackground="#c73652").pack(side="left", ipady=8, ipadx=12)

        tk.Button(bottom, text="📎", command=self._select_file, bg=ACCENT2,
                  fg="white", font=("Consolas", 14), bd=0).pack(
            side="left", ipadx=8, padx=(6, 0))

    # ---------- helpers ----------
    def append(self, text: str):
        self.chat_area.configure(state="normal")
        self.chat_area.insert("end", text + "\n")
        self.chat_area.configure(state="disabled")
        self.chat_area.yview("end")

    def on_message_threadsafe(self, msg: str):
        self.after(0, self.append, msg)

    def on_file_threadsafe(self, name: str, path: str):
        self.after(0, self.append, f"[arquivo recebido: {name} → {path}]")

    # ---------- ações ----------
    def connect_peer(self):
        raw = self.peer_entry.get().strip()
        if not raw:
            return
        host, _, port_s = raw.partition(":")
        port = int(port_s) if port_s else 5000
        self.append(f"[conectando a {host}:{port}...]")
        threading.Thread(target=self._do_connect, args=(host, port),
                         daemon=True).start()

    def _do_connect(self, host: str, port: int):
        try:
            sock = connect_to_peer(host, port, retries=2, delay=0.5)
        except ConnectionError as e:
            self.after(0, self.append, f"[falha: {e}]")
            return
        self.peer_socket = sock
        self.after(0, self.append, f"[conectado a {host}:{port}]")
        # escuta o socket de saída também (respostas do peer)
        from .network import _safe_handle
        threading.Thread(
            target=_safe_handle,
            args=(sock, self.key, self.on_message_threadsafe,
                  self.on_file_threadsafe, self.save_dir),
            daemon=True,
        ).start()

    def _send(self, event=None):
        msg = self.entry.get().strip()
        if not msg:
            return
        if not self.peer_socket:
            self.append("[conecte-se a um peer antes de enviar]")
            return
        self.entry.delete(0, "end")
        try:
            send_msg(self.peer_socket, f"{self.username}: {msg}", self.key)
            self.append(f"Você: {msg}")
        except OSError as e:
            self.append(f"[erro ao enviar: {e}]")
            self.peer_socket = None

    def _select_file(self):
        if not self.peer_socket:
            self.append("[conecte-se a um peer antes de enviar arquivos]")
            return
        path = filedialog.askopenfilename()
        if not path:
            return
        try:
            name = send_file(self.peer_socket, path, self.key)
            self.append(f"[arquivo enviado: {name}]")
        except OSError as e:
            self.append(f"[erro ao enviar arquivo: {e}]")


def start(username: str, password: str, peer: str | None = None,
          listen_port: int = 5000):
    """Sobe servidor + UI e, opcionalmente, conecta ao peer informado."""
    key = derive_key(password)
    app = ChatApp(username, key, listen_port)
    if peer:
        app.peer_entry.delete(0, "end")
        app.peer_entry.insert(0, peer)
        app.connect_peer()
    app.mainloop()
