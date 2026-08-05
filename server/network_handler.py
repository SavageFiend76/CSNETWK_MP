"""TCP connection wrapper used by the MTGNP server."""

from __future__ import annotations

import logging
import socket
import threading
from typing import Callable

from shared import protocol

class NetworkHandler:
    """Own one client socket and turn its byte stream into  PDUs.

    Socket reads happen in the connection's reader thread, but writes can be
    requested by the game manager or another reader thread.  ``_send_lock``
    prevents length-prefixed frames from being interleaved on the TCP stream.
    """

    def __init__(self, sock: socket.socket, address: tuple, *, verbose: bool = False):
        self.sock, self.address, self.verbose = sock, address, verbose
        self.player_id: str | None = None
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        self.log = logging.getLogger(__name__)

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def send(self, pdu: dict) -> None:
        if self.closed:
            raise protocol.ConnectionClosedError("attempted to send to closed client")
        if self.verbose:
            print(f"S -> {self.player_id or self.address}: {pdu}", flush=True)
        try:
            with self._send_lock:
                protocol.send_pdu(self.sock, pdu)
        except OSError as exc:
            self.close()
            raise protocol.ConnectionClosedError(str(exc)) from exc

    def serve(
        self,
        on_pdu: Callable[["NetworkHandler", dict], None],
        on_disconnect: Callable[["NetworkHandler"], None],
    ) -> None:
        """Read and dispatch PDUs until this peer disconnects."""
        try:
            while not self.closed:
                raw = protocol.recv_pdu(self.sock)
                if self.verbose:
                    print(f"{self.player_id or self.address} -> S: {raw}", flush=True)
                on_pdu(self, raw)
        except protocol.ConnectionClosedError:
            pass
        except OSError:
            pass
        finally:
            self.close()
            on_disconnect(self)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
