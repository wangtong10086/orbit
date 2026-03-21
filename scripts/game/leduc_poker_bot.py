"""Leduc Poker bot strategy.

v1: 固定决策表 → 50% vs MCTS (eval 45.9%)
v2: equity评分+bluff → 40% vs MCTS ← 回退! bluff 浪费筹码
v3: 回归决策表核心 + 对手raise感知 + 更好的think
    关键: Leduc只有6张牌(J♠J♥Q♠Q♥K♠K♥), 最优策略接近确定性
"""


def leduc_poker_bot(state, player):
    info = state.information_state_string(player)
    legal = state.legal_actions(player)

    private_card = int(info.split("Private: ")[1].split("]")[0])
    rank = private_card // 2  # 0=J, 1=Q, 2=K
    rank_name = ["J", "Q", "K"][rank]
    suit = "♠" if private_card % 2 == 0 else "♥"

    has_public = "Public:" in info
    public_rank = -1
    public_name = ""
    if has_public:
        public_card = int(info.split("Public: ")[1].split("]")[0])
        public_rank = public_card // 2
        public_name = ["J", "Q", "K"][public_rank]
    has_pair = has_public and rank == public_rank

    # Detect if opponent raised
    round_str = "Round 2" if has_public else "Round 1"
    # Count opponent actions in history
    opp_raised = info.count("2") > (1 if 2 in legal else 0)

    # Core strategy (near-optimal for Leduc)
    if has_pair:
        action = 2 if 2 in legal else 1
        think = (f"{round_str}: I hold {rank_name}{suit} and the public card is {public_name} — "
                 f"I have a pair, which is the strongest possible hand in Leduc poker. "
                 f"With only 6 cards in the deck, opponent cannot have a pair too (only 2 of each rank). "
                 f"{'Raising' if action == 2 else 'Calling'} to extract maximum value from this dominant position.")
    elif rank == 2:  # K
        if has_public:
            if public_rank == 2:
                # Public K, I have K = pair (handled above, shouldn't reach here)
                action = 2 if 2 in legal else 1
                think = f"{round_str}: K with K public — pair! Maximum value."
            else:
                # Public J or Q, I have K unpaired
                if opp_raised:
                    action = 1 if 1 in legal else 0
                    think = (f"{round_str}: holding K{suit} against public {public_name}. No pair, but K is the highest unpaired rank. "
                             f"Opponent raised, which could mean they paired with {public_name} or are bluffing. "
                             f"K-high still beats unpaired Q and J, so calling is correct — folding would surrender too much equity.")
                else:
                    action = 2 if 2 in legal else 1
                    think = (f"{round_str}: K{suit} is the strongest unpaired hand against public {public_name}. "
                             f"Opponent checked or called, suggesting they likely don't have a pair of {public_name}s. "
                             f"Raising to charge draws and potentially win a bigger pot with the best high card.")
        else:
            action = 2 if 2 in legal else 1
            think = (f"{round_str}: K{suit} is the best possible private card in Leduc. "
                     f"Before the public card, K beats both Q and J in a showdown. "
                     f"Raising now builds the pot and puts pressure on weaker hands to fold or pay to continue.")
    elif rank == 1:  # Q
        if has_public:
            if public_rank == 0:  # Public J
                if opp_raised:
                    action = 1 if 1 in legal else 0
                    think = (f"{round_str}: Q{suit} against public J. Opponent raised — they might have a J pair. "
                             f"My Q-high beats unpaired K but loses to J-pair. "
                             f"Calling cautiously since Q is still second-best unpaired hand.")
                else:
                    action = 1 if 1 in legal else (2 if 2 in legal else 0)
                    think = (f"{round_str}: Q{suit} against public J, opponent didn't raise. "
                             f"Q-high beats unpaired J and K-high doesn't pair either. "
                             f"Reasonable showdown equity — calling to contest the pot.")
            elif public_rank == 2:  # Public K
                if opp_raised:
                    # Opponent raised on K board — very likely has K pair
                    action = 0 if 0 in legal else 1
                    if action == 0:
                        think = (f"{round_str}: Q{suit} against public K, and opponent raised. "
                                 f"An opponent raise on a K board strongly suggests they hold K for a pair. "
                                 f"My Q-high loses to K-pair and can only beat J-high — the odds don't justify continuing. "
                                 f"Folding to avoid losing more chips in a dominated position.")
                    else:
                        think = (f"{round_str}: Q{suit} against public K with aggressive opponent. "
                                 f"Very likely facing K-pair. Only calling because fold isn't available.")
                else:
                    action = 1 if 1 in legal else 0
                    think = (f"{round_str}: Q{suit} against public K, opponent was passive. "
                             f"No raise suggests they may not have K. Q-high has some showdown value. "
                             f"Calling to see if opponent was slow-playing or genuinely weak.")
            else:  # Public Q
                action = 2 if 2 in legal else 1  # I have a pair!
                think = f"{round_str}: Q{suit} pairs with public Q! Raising for value."
        else:
            action = 1 if 1 in legal else 2
            think = (f"{round_str}: Q{suit} is the middle rank. It beats J but loses to K. "
                     f"With the public card still unknown, there's a 1/3 chance of pairing on the next card. "
                     f"Calling keeps the investment small while retaining the option to improve or fold in Round 2.")
    else:  # J
        if has_public:
            if public_rank == 0:  # Public J — I have pair!
                action = 2 if 2 in legal else 1
                think = f"{round_str}: J{suit} pairs with public J! Strongest hand possible. Raising for maximum value."
            else:
                # Public Q or K, I have J = worst
                # J against non-J public card = worst position, always fold if possible
                action = 0 if 0 in legal else 1
                if action == 0:
                    think = (f"{round_str}: J{suit} against public {public_name} — worst possible position. "
                             f"{'Opponent raised, strongly suggesting a pair or K-high. ' if opp_raised else 'Even without a raise, '}"
                             f"J-high loses to K-high, Q-high, and any pair. "
                             f"Only chance of winning is if opponent also has J, but that's unlikely given they continued. "
                             f"Folding to preserve chips for better spots.")
                else:
                    think = (f"{round_str}: J{suit} against public {public_name}. Worst hand possible. "
                             f"Cannot fold, so calling minimally. Expecting to lose this pot.")
        else:
            action = 1 if 1 in legal else 0
            think = (f"{round_str}: J{suit} is the weakest private card. It loses to both Q and K in a showdown. "
                     f"However, there's a 1/3 chance the public card is J, giving me a pair. "
                     f"Calling the minimum to see if I improve. The investment is small relative to the potential payoff of hitting a pair.")

    return action, think
