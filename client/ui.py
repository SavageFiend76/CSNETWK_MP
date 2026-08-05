from client.client import GameClient
from client.input_handler import InputHandler
from shared.messages import to_dict

class GameUI:
    def __init__(self):
        self.client = GameClient()
        self.handler = None

    def connect(self):
        if self.client.connect():
            player_id = input("Enter player ID: ").strip()
            self.handler = InputHandler(player_id)
            print(f"Welcome, {player_id}!")
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
                self.receive_once()

            elif choice == "2":
                pdu = self.handler.pass_priority()
                self.client.send(pdu)
                print("PRIORITY_PASS sent.")
                self.receive_once()

            elif choice == "3":
                card = input("Card ID: ").strip()
                pdu = self.handler.play_land(card)
                self.client.send(pdu)
                print("PLAY_LAND sent.")
                self.receive_once()

            elif choice == "4":
                pdu = self.handler.concede()
                self.client.send(pdu)
                print("CONCEDE sent.")
                self.receive_once()
                
            elif choice == "5":
                self.client.disconnect()
                break

            else:
                print("Invalid choice.")

    def receive_once(self):
        """
        Receive one PDU from the server and display it.
        """
        try:
            pdu = self.client.receive()
            print("\n[SERVER]")
            print(to_dict(pdu))

        except ConnectionError as e:
            print(f"[CONNECTION ERROR] {e}")

        except Exception as e:
            print(f"[ERROR] {e}")

if __name__ == "__main__":
    GameUI().run()