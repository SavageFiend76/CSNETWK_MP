import socket

from shared.constants import PORT
from shared.protocol import (
    send_pdu,
    recv_pdu,
    validate_envelope,
    ConnectionClosedError,
)
from shared.messages import (
    PDU,
    to_dict,
    parse,
)

class GameClient:
    def __init__(self, host="127.0.0.1", port=PORT):
        self.host = host
        self.port = port
        self.socket = None

    def connect(self):
        """
        Establish a TCP connection to the game server.

        Returns:
            True if the connection succeeds.
            False if the connection fails.
        """
        try:
            # Create IPv4 TCP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # Prevent recv() from blocking forever
            self.socket.settimeout(5)

            # Connect to the server
            self.socket.connect((self.host, self.port))

            print(f"[CONNECTED] {self.host}:{self.port}")
            return True

        except (socket.timeout, ConnectionRefusedError) as e:
            print(f"[ERROR] Could not connect: {e}")
            self.socket = None
            return False

        except OSError as e:
            print(f"[SOCKET ERROR] {e}")
            self.socket = None
            return False

    @property
    def connected(self):
        return self.socket is not None

    def disconnect(self):
        """
        Gracefully disconnect from the server.
        """
        if self.socket is not None:
            try:
                self.socket.close()
                print("[DISCONNECTED] Connection closed.")
            except OSError as e:
                print(f"[ERROR] Failed to close socket: {e}")
            finally:
                self.socket = None

    @property
    def connected(self):
        """
        Returns True if currently connected to the server.
        """
        return self.socket is not None

    def send(self, pdu: PDU):
        """
        Send a PDU object to the server.
        """
        if not self.connected:
            raise ConnectionError("Not connected to the server.")

        try:
            send_pdu(self.socket, to_dict(pdu))

        except OSError as e:
            print(f"[SEND ERROR] {e}")
            self.disconnect()
            raise

    def receive(self) -> PDU:
        """
        Receive one PDU from the server.
        """
        if not self.connected:
            raise ConnectionError("Not connected to the server.")

        try:
            raw = recv_pdu(self.socket)

            validate_envelope(raw)

            return parse(raw)

        except ConnectionClosedError:
            print("[DISCONNECTED] Server closed the connection.")
            self.disconnect()
            raise

        except OSError as e:
            print(f"[RECEIVE ERROR] {e}")
            self.disconnect()
            raise

    def reconnect(self):
        """
        Reconnect to the server.
        """
        self.disconnect()
        return self.connect()

if __name__ == "__main__":
    client = GameClient()

    if client.connect():
        print("Connection successful!")
        client.disconnect()
    else:
        print("Failed to connect.")