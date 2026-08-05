"""
Temporary GameManager stub.

This exists only to let the server boot and test the networking layer.
Replace it with the real implementation once it is available.
"""

class GameManager:
    def __init__(self, send_to, broadcast):
        self.send_to = send_to
        self.broadcast = broadcast

    def receive(self, connection, raw):
        print(f"[GameManager Stub] Received: {raw}")

        if raw.get("type") == "PLAYER_READY":
            connection.send({
            "type": "PONG",
            "seq_num": raw["seq_num"],
            "timestamp": 0,
            })

        # Claim player ID after PLAYER_READY.
        if raw.get("type") == "PLAYER_READY":
            player = raw["player_id"]

            # Temporarily claim the ID
            connection.player_id = player

            self.send_to(
                player,
                {
                    "type": "PONG",
                    "seq_num": raw["seq_num"],
                    "timestamp": 0,
                },
            )

            return raw["player_id"]

    def disconnected(self, connection):
        print(f"[GameManager Stub] Disconnect: {connection.player_id}")