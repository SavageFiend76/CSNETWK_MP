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
        print("5. Exit")

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
                pdu = self.handler.pass_priority()
                self.client.send(pdu)
                print("PRIORITY_PASS sent.")

            elif choice == "3":
                card = input("Card ID: ").strip()
                pdu = self.handler.play_land(card)
                self.client.send(pdu)
                print("PLAY_LAND sent.")

            elif choice == "4":
                pdu = self.handler.concede()
                self.client.send(pdu)
                print("CONCEDE sent.")
                
            elif choice == "5":
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