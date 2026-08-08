import threading
from client.client import GameClient
from client.input_handler import InputHandler
from shared.messages import to_dict

class GameUI:
    def __init__(self):
        self.client = GameClient()
        self.handler = None
        self.running = True
        self.receiver = None
        self.mulligan_token = None
        self.priority_token = None
        self.priority_player = None

    def connect(self):
        if self.client.connect():
            player_id = input("Enter player ID: ").strip()
            self.handler = InputHandler(player_id)
            print(f"Welcome, {player_id}!")
            self.receiver = threading.Thread(
            target=self.listen,
            daemon=True,
            )
            self.receiver.start()
        else:
            print("Unable to connect to server.")

    def show_menu(self):
        print("\n==== MTG Client ====")
        print("1. Ready")
        print("2. Pass Priority")
        print("3. Play Land")
        print("4. Concede")
        print("5. keep hand")
        print("6. Mulligan")
        print("7. Declare Attackers")
        print("8. Exit")

    def run(self):
        self.connect()

        if self.handler is None:
            return

        while True:
            self.show_menu()

            choice = input("Choice: ").strip()

            if choice == "1":
                deck = input("Deck (comma separated): ").split(",")
                pdu = self.handler.ready([c.strip() for c in deck])
                self.client.send(pdu)
                print("PLAYER_READY sent.")

            elif choice == "2":
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                token = self.priority_token
                pdu = self.handler.pass_priority(token)
                self.client.send(pdu)
                print(f"PRIORITY_PASS sent (token={token}).")
                self.priority_token = None

            elif choice == "3":
                card = input("Card ID: ").strip()
                print(f"[DEBUG] priority_token={self.priority_token!r}")

                pdu = self.handler.play_land(card, self.priority_token)

                print(f"[DEBUG] generated PDU={to_dict(pdu)}")
                self.client.send(pdu)

                print(f"PLAY_LAND sent (token={self.priority_token}).")

            elif choice == "4":
                pdu = self.handler.concede()
                self.client.send(pdu)
                print("CONCEDE sent.")

            elif choice == "5":
                if self.mulligan_token is None:
                    print("No mulligan token received yet.")
                    continue

                pdu = self.handler.mulligan(
                keep=True,
                token=self.mulligan_token,
                )
                self.client.send(pdu)
                print(f"MULLIGAN KEEP sent (token={self.mulligan_token}).")

            elif choice == "6":
                if self.mulligan_token is None:
                    print("No mulligan token received yet.")
                    continue

                pdu = self.handler.mulligan(
                    keep=False,
                    token=self.mulligan_token,
                )
                self.client.send(pdu)
                print(f"MULLIGAN sent (token={self.mulligan_token}).")

            elif choice == "7":
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                if self.priority_player != self.handler.player_id:
                    print("You do not have priority.")
                    continue

                attackers = input(
                    "Attacker card IDs (comma separated, blank for none): "
                ).strip()

                attacker_list = (
                [a.strip() for a in attackers.split(",")]
                if attackers
                else []
                )

                token = self.priority_token

                pdu = self.handler.declare_attackers(
                    attacker_list,
                    token
                )

                print(f"[DEBUG] generated PDU={to_dict(pdu)}")

                self.client.send(pdu)

                print(f"DECLARE_ATTACKERS sent (token={token}).")

                self.priority_token = None
            
            elif choice == "8":
                self.running = False
                self.client.disconnect()
                break

            else:
                print("Invalid choice.")

    def receive_once(self):
        """
        Receive all currently available PDUs from the server.
        """
        while True:
            try:
                pdu = self.client.receive()
                print("\n[SERVER]")
                print(to_dict(pdu))

            except TimeoutError:
                # No more packets waiting.
                break

            except ConnectionError as e:
                print(f"[CONNECTION ERROR] {e}")
                break

            except Exception as e:
                # socket timeout also ends the receive loop
                if "timed out" in str(e).lower():
                    break

                print(f"[ERROR] {e}")
                break

    def listen(self):
        while self.running and self.client.connected:
            try:
                pdu = self.client.receive()

                if (
                    pdu.TYPE == "GAME_STATE_UPDATE"
                    and getattr(pdu, "state", {}).get("phase") == "MULLIGAN"
                ):
                    self.mulligan_token = pdu.seq_num
                if pdu.TYPE == "PRIORITY_GRANT":
                    self.priority_token = pdu.seq_num
                    self.priority_player = pdu.player_id

                print("\n[SERVER]")
                print(to_dict(pdu))

            except TimeoutError:
                continue

            except ConnectionError:
                break

            except Exception as e:
                print(f"[ERROR] {e}")
                break

if __name__ == "__main__":
    GameUI().run()