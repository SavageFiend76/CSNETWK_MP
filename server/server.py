"""To Run: ``python -m server.server --verbose``."""

from __future__ import annotations

import argparse
import socket
import threading

from server.game_manager import GameManager
from server.network_handler import NetworkHandler
from shared import constants as c


class MTGNPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = c.PORT, *, verbose: bool = False):
        self.host, self.port, self.verbose = host, port, verbose
        self.connections: list[NetworkHandler] = []
        self.connections_by_player: dict[str, NetworkHandler] = {}
        self._connections_lock = threading.RLock()
        self.game = GameManager(self._send_to, self._broadcast)

    def _send_to(self, player_id: str, pdu: dict) -> None:
        connection = self.connections_by_player.get(player_id)
        if connection: connection.send(pdu)

    def _broadcast(self, pdu: dict) -> None:
        for connection in list(self.connections):
            if not connection.closed: connection.send(pdu)

    def _on_pdu(self, connection: NetworkHandler, raw: dict) -> None:
        claimed = self.game.receive(connection, raw)
        if claimed:
            connection.player_id = claimed
            self.connections_by_player[claimed] = connection

    def _on_disconnect(self, connection: NetworkHandler) -> None:
        with self._connections_lock:
            if connection in self.connections: self.connections.remove(connection)
            if connection.player_id: self.connections_by_player.pop(connection.player_id, None)
        self.game.disconnected(connection)

    def serve_forever(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port)); listener.listen(2)
            print(f"MTGNP server listening on {self.host}:{self.port}", flush=True)
            while True:
                client, address = listener.accept()
                with self._connections_lock:
                    if len(self.connections) >= 2:
                        client.close()  # RFC 5.1: refuse third and later connections.
                        continue
                    connection = NetworkHandler(client, address, verbose=self.verbose)
                    self.connections.append(connection)
                threading.Thread(target=connection.serve, args=(self._on_pdu, self._on_disconnect), daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="MTGNP authoritative game server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=c.PORT)
    parser.add_argument("--verbose", action="store_true", help="log every sent and received PDU")
    args = parser.parse_args()
    MTGNPServer(args.host, args.port, verbose=args.verbose).serve_forever()


if __name__ == "__main__":
    main()
