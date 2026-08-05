from shared.messages import (
    PlayerReady,
    PriorityPass,
    Concede,
    PlayLand,
    CastSpell,
    DeclareAttackers,
    DeclareBlockers,
    Discard,
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

    def pass_priority(self):
        return PriorityPass(
            seq_num=self.next_seq()
        )

    def concede(self):
        return Concede(
            seq_num=self.next_seq(),
            player_id=self.player_id
        )

    def play_land(self, card_id: str):
        return PlayLand(
            seq_num=self.next_seq(),
            card_id=card_id
        )

    def cast_spell(self, card_id: str, targets=None, mana_payment=None):
        if targets is None:
            targets = []
        if mana_payment is None:
            mana_payment = {}

        return CastSpell(
            seq_num=self.next_seq(),
            card_id=card_id,
            targets=targets,
            mana_payment=mana_payment
        )

    def declare_attackers(self, attackers: list):
        return DeclareAttackers(
            seq_num=self.next_seq(),
            attackers=attackers
        )

    def declare_blockers(self, blockers: list):
        return DeclareBlockers(
            seq_num=self.next_seq(),
            blockers=blockers
        )

    def discard(self, card_ids: list):
        return Discard(
            seq_num=self.next_seq(),
            card_ids=card_ids
        )

if __name__ == "__main__":
    handler = InputHandler("player1")

    print(handler.ready(["Island_001", "Mountain_001"]))
    print(handler.pass_priority())
    print(handler.play_land("Island_001"))
    print(handler.concede())