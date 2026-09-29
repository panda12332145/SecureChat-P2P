#!/usr/bin/env python3
"""Ponto de entrada do SecureChat-P2P.

Uso:
  python main.py                      # prompts interativos
  python main.py --name Ana --peer 192.168.0.10:5000 --port 5001
  python main.py --name Ana --password 'segredo' --no-gui   # modo teste (sem Tk)
"""
import argparse
import getpass
import socket
import threading

from src.crypto import derive_key
from src.network import handle_peer, listen_for_peers, start_server


def parse_args():
    p = argparse.ArgumentParser(description="SecureChat P2P")
    p.add_argument("--name", help="seu nome de usuário")
    p.add_argument("--password", help="senha pré-compartilhada (a MESMA nos dois lados)")
    p.add_argument("--peer", help="peer inicial no formato host[:porta]")
    p.add_argument("--port", type=int, default=5000, help="porta local (padrão 5000)")
    p.add_argument("--no-gui", action="store_true",
                   help="sem interface gráfica: só servidor de recepção (útil p/ testes)")
    return p.parse_args()


def main():
    args = parse_args()
    name = args.name or input("Seu nome: ").strip()
    password = args.password or getpass.getpass("Senha compartilhada: ")
    key = derive_key(password)

    srv = start_server(args.port)
    print(f"[servidor escutando na porta {args.port}]")

    save_dir = None  # padrão: ~/Downloads
    threading.Thread(target=listen_for_peers,
                     args=(srv, key, print, lambda n, p: print(f"[arquivo salvo em {p}]"), save_dir),
                     daemon=True).start()

    if args.no_gui:
        print("[modo --no-gui: recebendo mensagens. Ctrl+C para sair]")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            return

    # Interface gráfica (precisa de display)
    from src.chat_ui import ChatApp
    app = ChatApp(name, key, args.port)
    if args.peer:
        host, _, port_s = args.peer.partition(":")
        app.peer_entry.delete(0, "end")
        app.peer_entry.insert(0, f"{host}:{port_s or args.port}")
        app.connect_peer()
    app.mainloop()


if __name__ == "__main__":
    main()
