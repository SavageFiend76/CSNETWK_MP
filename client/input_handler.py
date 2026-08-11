from shared.messages import MulliganChoice

from shared.messages import (
    PlayerReady,
    PriorityPass,
    Concede,
    PlayLand,
    CastSpell,
    DeclareAttackers,
    DeclareBlockers,
    Discard,
    ActivateAbility,
    TriggerOrderResponse,
    TriggerChoiceResponse,
    AssignDamageOrder,
)

class InputHandler:
    def __init__(self, player_id: str):
        self.player_id = player_id
        self.seq_num = 0

    def next_seq(self):
        self.seq_num += 1
        return self.seq_num

    def ready(self, deck_list: list):
        return PlayerReady(
            seq_num=self.next_seq(),
            player_id=self.player_id,
            deck_list=deck_list
        )

    def pass_priority(self, token: int):
        return PriorityPass(
            seq_num=token
        )

    def concede(self, token: int):
        return Concede(
            seq_num=token,
            player_id=self.player_id
        )

    def play_land(self, card_id: str, token: int):
        card_id = card_id.strip().lower()
        
        return PlayLand(
            seq_num=token,
            card_id=card_id
        )

    def cast_spell(self, card_id: str, token: int, targets=None, mana_payment=None):
        if targets is None:
            targets = []
        if mana_payment is None:
            mana_payment = {}

        return CastSpell(
            seq_num=token,
            card_id=card_id,
            targets=targets,
            mana_payment=mana_payment
        )

    def declare_attackers(self, attackers: list, token: int):
        return DeclareAttackers(
            seq_num=token,
            attackers=attackers
        )

    def declare_blockers(self, blockers: list, token: int):
        return DeclareBlockers(
            seq_num=token,
            blockers=blockers
        )

    def discard(self, card_ids: list, token: int):
        return Discard(
            seq_num=token,
            card_ids=card_ids
        )

    def mulligan(self, keep: bool, token: int, cards_to_bottom=None):
        if cards_to_bottom is None:
            cards_to_bottom = []

        return MulliganChoice(
            seq_num=token,
            keep=keep,
            cards_to_bottom=cards_to_bottom,
        )

    def activate_ability(self, source_id: str, ability_index: int, token: int, targets=None, cost_payment=None):
        if targets is None:
            targets = []
        if cost_payment is None:
            cost_payment = {}

        return ActivateAbility(
            seq_num=token,
            source_id=source_id,
            ability_index=ability_index,
            targets=targets,
            cost_payment=cost_payment
        )

    def trigger_order_response(self, ordered_trigger_ids: list, token: int):
        return TriggerOrderResponse(
            seq_num=token,
            ordered_trigger_ids=ordered_trigger_ids
        )

    def trigger_choice_response(self, trigger_id: str, accept: bool, token: int, chosen_target=None):
        return TriggerChoiceResponse(
            seq_num=token,
            trigger_id=trigger_id,
            accept=accept,
            chosen_target=chosen_target
        )

    def assign_damage_order(self, attacker_id: str, blocker_order: list, token: int):
        return AssignDamageOrder(
            seq_num=token,
            attacker_id=attacker_id,
            blocker_order=blocker_order
        )

if __name__ == "__main__":
    handler = InputHandler("player1")

    print(handler.ready(["Island_001", "Mountain_001"]))
    print(handler.pass_priority(token=1))
    print(handler.play_land("Island_001", token=1))
    print(handler.concede(token=1))