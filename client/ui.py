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
        self.cards_to_bottom = []
        self.mulligan_count = 0
        self.last_seq_num = None
        self.discard_token = None
        self.trigger_order_token = None
        self.trigger_order_ids = None
        self.trigger_choice_token = None
        self.trigger_choice_id = None

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
        print("8. Cast Spell")
        print("9. Declare Blockers")
        print("10. Discard")
        print("11. Activate Ability")
        print("12. Trigger Order Response")
        print("13. Trigger Choice Response")
        print("14. Assign Damage Order")
        print("15. Exit")

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
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                if self.priority_player != self.handler.player_id:
                    print("You do not have priority.")
                    continue

                card = input("Card ID: ").strip().lower()

                token = self.priority_token

                pdu = self.handler.play_land(card, token)

                print(f"[DEBUG] generated PDU={to_dict(pdu)}")

                self.client.send(pdu)

                print(f"PLAY_LAND sent (token={token}).")
                self.priority_token = None

            elif choice == "4":
                if self.last_seq_num is None:
                    print("No server message received yet, cannot concede.")
                    continue

                pdu = self.handler.concede(self.last_seq_num)

                self.client.send(pdu)
                print("CONCEDE sent.")

            elif choice == "5":
                if self.mulligan_token is None:
                    print("No mulligan token received yet.")
                    continue

                print(
                    f"You must bottom exactly "
                    f"{self.mulligan_count} card(s)."
                )

                bottom_input = input(
                    "Cards to bottom (comma separated): "
                ).strip()

                if bottom_input:
                    cards_to_bottom = [
                    card.strip()
                    for card in bottom_input.split(",")
                        if card.strip()
                    ]
                else:
                    cards_to_bottom = []

                if len(cards_to_bottom) != self.mulligan_count:
                    print(
                        f"Invalid number of cards. "
                        f"You must bottom exactly {self.mulligan_count}."
                    )
                    continue

                token = self.mulligan_token

                pdu = self.handler.mulligan(
                    keep=True,
                    token=token,
                    cards_to_bottom=cards_to_bottom,
                )

                self.client.send(pdu)

                print(
                    f"MULLIGAN KEEP sent "
                    f"(token={token}, "
                    f"bottoming={cards_to_bottom})."
                )

                self.mulligan_token = None
                self.mulligan_count = 0

            elif choice == "6":
                if self.mulligan_token is None:
                    print("No mulligan token received yet.")
                    continue

                token = self.mulligan_token

                pdu = self.handler.mulligan(
                    keep=False,
                    token=token,
                    cards_to_bottom=[],
                )

                self.client.send(pdu)

                print(f"MULLIGAN sent (token={token}).")

                self.mulligan_token = None
                self.mulligan_count += 1

                print(
                    f"Mulligan #{self.mulligan_count}. "
                    f"When you keep, you must bottom exactly "
                    f"{self.mulligan_count} card(s)."
                )
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
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                card = input("Card ID: ").strip()
                targets_raw = input("Targets (comma separated, blank for none): ").strip()
                targets = [t.strip() for t in targets_raw.split(",")] if targets_raw else []

                mana_raw = input("Mana payment e.g. R:1,U:2 (blank for none): ").strip()
                mana_payment = {}
                if mana_raw:
                    for pair in mana_raw.split(","):
                        color, amount = pair.split(":")
                        mana_payment[color.strip()] = int(amount.strip())

                token = self.priority_token
                pdu = self.handler.cast_spell(card, token, targets=targets, mana_payment=mana_payment)

                self.client.send(pdu)

                print(f"CAST_SPELL sent (token={token}).")
                self.priority_token = None

            elif choice == "9":
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                blockers_raw = input(
                    "Blocks as creature_id:blocking_id pairs, comma separated (blank for none): "
                ).strip()
                blockers = []
                if blockers_raw:
                    for pair in blockers_raw.split(","):
                        creature_id, blocking_id = pair.split(":")
                        blockers.append({
                            "creature_id": creature_id.strip(),
                            "blocking_id": blocking_id.strip(),
                        })

                token = self.priority_token
                pdu = self.handler.declare_blockers(blockers, token)

                self.client.send(pdu)

                print(f"DECLARE_BLOCKERS sent (token={token}).")
                self.priority_token = None

            elif choice == "10":
                if self.discard_token is None:
                    print("No discard token available.")
                    continue

                cards_raw = input("Card IDs to discard (comma separated): ").strip()
                card_ids = [c.strip() for c in cards_raw.split(",")] if cards_raw else []

                token = self.discard_token
                pdu = self.handler.discard(card_ids, token)
                
                self.client.send(pdu)

                print(f"DISCARD sent (token={token}).")
                self.discard_token = None
            
            elif choice == "11":
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                source = input("Source permanent ID: ").strip()
                ability_index = int(input("Ability index (0-based): ").strip())
                targets_raw = input("Targets (comma separated, blank for none): ").strip()
                targets = [t.strip() for t in targets_raw.split(",")] if targets_raw else []

                tap_raw = input("Requires tap? (y/n): ").strip().lower()
                cost_payment = {"tap": tap_raw == "y", "mana": {}}

                token = self.priority_token
                pdu = self.handler.activate_ability(source, ability_index, token, targets=targets, cost_payment=cost_payment)

                self.client.send(pdu)

                print(f"ACTIVATE_ABILITY sent (token={token}).")
                self.priority_token = None

            elif choice == "12":
                if self.trigger_order_token is None:
                    print("No trigger order request pending.")
                    continue

                print(f"Triggers to order: {self.trigger_order_ids}")
                order_raw = input("Enter trigger_ids in desired stack order (comma separated): ").strip()
                ordered = [t.strip() for t in order_raw.split(",")] if order_raw else []

                token = self.trigger_order_token
                pdu = self.handler.trigger_order_response(ordered, token)

                self.client.send(pdu)

                print(f"TRIGGER_ORDER_RESPONSE sent (token={token}).")
                self.trigger_order_token = None
                self.trigger_order_ids = None

            elif choice == "13":
                if self.trigger_choice_token is None:
                    print("No trigger choice pending.")
                    continue

                accept_raw = input(f"Accept trigger {self.trigger_choice_id}? (y/n): ").strip().lower()
                accept = accept_raw == "y"
                chosen_target = None
                if accept:
                    target_raw = input("Chosen target (blank if none required): ").strip()
                    chosen_target = target_raw if target_raw else None

                token = self.trigger_choice_token
                pdu = self.handler.trigger_choice_response(self.trigger_choice_id, accept, token, chosen_target=chosen_target)

                self.client.send(pdu)

                print(f"TRIGGER_CHOICE_RESPONSE sent (token={token}).")
                self.trigger_choice_token = None
                self.trigger_choice_id = None

            elif choice == "14":
                if self.priority_token is None:
                    print("No priority token available.")
                    continue

                attacker_id = input("Multiply-blocked attacker ID: ").strip()
                order_raw = input("Blocker IDs in damage order (comma separated): ").strip()
                blocker_order = [b.strip() for b in order_raw.split(",")] if order_raw else []

                token = self.priority_token
                pdu = self.handler.assign_damage_order(attacker_id, blocker_order, token)

                self.client.send(pdu)

                print(f"ASSIGN_DAMAGE_ORDER sent (token={token}).")
                self.priority_token = None

            elif choice == "15":
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
                self.last_seq_num = pdu.seq_num

                if (
                    pdu.TYPE == "GAME_STATE_UPDATE"
                    and getattr(pdu, "state", {}).get("phase") == "MULLIGAN"
                ):
                    self.mulligan_token = pdu.seq_num
                if pdu.TYPE == "PRIORITY_GRANT":
                    self.priority_token = pdu.seq_num
                    self.priority_player = pdu.player_id
                if (
                    pdu.TYPE == "PHASE_TRANSITION"
                    and getattr(pdu, "to_phase", None) == "DECLARE_ATTACKERS"
                ):
                    self.priority_token = pdu.seq_num
                    self.priority_player = pdu.active_player
                if (
                    pdu.TYPE == "GAME_STATE_UPDATE"
                    and getattr(pdu, "state", {}).get("phase") == "CLEANUP"
                    and len(getattr(pdu, "state", {}).get("hand", [])) > 7
                ):
                    self.discard_token = pdu.seq_num
                if pdu.TYPE == "TRIGGER_ORDER":
                    self.trigger_order_token = pdu.seq_num
                    self.trigger_order_ids = pdu.trigger_ids
                if pdu.TYPE == "TRIGGER_CHOICE":
                    self.trigger_choice_token = pdu.seq_num
                    self.trigger_choice_id = pdu.trigger_id

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