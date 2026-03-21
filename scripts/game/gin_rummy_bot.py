"""Gin Rummy bot: meld-aware + near-meld evaluation + smart knock timing."""


def gin_rummy_bot(state, player):
    legal = state.legal_actions(player)
    if not legal:
        return 0, "No legal moves."
    if len(legal) == 1:
        return legal[0], "Only one legal action available."

    CARD_NAMES = ['A', '2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K']
    SUIT_NAMES = ['s', 'c', 'd', 'h']

    def card_rank(cid): return cid % 13
    def card_suit(cid): return cid // 13
    def card_name(cid): return CARD_NAMES[card_rank(cid)] + SUIT_NAMES[card_suit(cid)]

    def deadwood_value(cid):
        r = card_rank(cid)
        if r == 0: return 1
        if r >= 9: return 10
        return r + 1

    def find_melds(hand):
        melds = []
        by_rank = {}
        for c in hand:
            by_rank.setdefault(card_rank(c), []).append(c)
        for r, cards in by_rank.items():
            if len(cards) >= 3:
                melds.append(tuple(sorted(cards[:3])))
                if len(cards) >= 4:
                    melds.append(tuple(sorted(cards)))
        by_suit = {}
        for c in hand:
            by_suit.setdefault(card_suit(c), []).append(c)
        for s, cards in by_suit.items():
            ranks = sorted(set(card_rank(c) for c in cards))
            run = [ranks[0]]
            for i in range(1, len(ranks)):
                if ranks[i] == run[-1] + 1:
                    run.append(ranks[i])
                else:
                    if len(run) >= 3:
                        melds.append(tuple(s * 13 + r for r in run))
                    run = [ranks[i]]
            if len(run) >= 3:
                melds.append(tuple(s * 13 + r for r in run))
        return melds

    def calc_deadwood(hand):
        melds = find_melds(hand)
        if not melds:
            return sum(deadwood_value(c) for c in hand), set()
        remaining = set(hand)
        melded = set()
        changed = True
        while changed:
            changed = False
            best_meld, best_saving = None, 0
            for m in melds:
                if all(c in remaining for c in m):
                    saving = sum(deadwood_value(c) for c in m)
                    if saving > best_saving:
                        best_saving = saving
                        best_meld = m
            if best_meld:
                for c in best_meld:
                    remaining.discard(c)
                    melded.add(c)
                changed = True
        return sum(deadwood_value(c) for c in remaining), melded

    def near_meld_value(cid, hand):
        r, s = card_rank(cid), card_suit(cid)
        value = 0
        same_rank = [c for c in hand if card_rank(c) == r and c != cid]
        value += len(same_rank) * 3
        same_suit_ranks = sorted([card_rank(c) for c in hand if card_suit(c) == s and c != cid])
        for sr in same_suit_ranks:
            if abs(sr - r) == 1: value += 4
            elif abs(sr - r) == 2: value += 1
        return value

    info = state.information_state_string(player)
    hand = [cid for cid in range(52) if card_name(cid) in info]

    has_draw_upcard = 52 in legal
    has_draw_stock = 53 in legal
    has_pass = 54 in legal
    has_knock = 55 in legal
    discard_actions = [a for a in legal if a < 52]

    dw, melded = calc_deadwood(hand)
    melds = find_melds(hand)
    hand_str = ", ".join(card_name(c) for c in sorted(hand))
    melded_str = ", ".join(card_name(c) for c in sorted(melded))

    # Knock: only with very low deadwood
    if has_knock:
        if dw <= 5:
            return 55, f"Deadwood is only {dw} with melds [{melded_str}]. This is well below the knock threshold — ending the round now locks in a strong position before opponent can improve their hand."
        elif dw <= 8:
            return 55, f"Deadwood at {dw} is comfortably knockable. Melds [{melded_str}] are solid. Waiting longer risks opponent reaching gin or improving enough to undercut."
        elif len(melds) >= 3:
            return 55, f"Deadwood is {dw} but {len(melds)} melds are formed. Knocking now despite slightly higher deadwood because opponent could catch up if we wait."

    # Draw phase
    if has_draw_upcard or has_draw_stock:
        upcard_cid = None
        if "Upcard: " in info:
            uc_str = info.split("Upcard: ")[-1][:2].strip()
            if uc_str != "XX":
                for cid in range(52):
                    if card_name(cid) == uc_str:
                        upcard_cid = cid
                        break

        if has_pass and not has_draw_stock:
            if upcard_cid is not None:
                test_hand = hand + [upcard_cid]
                dw_with, _ = calc_deadwood(test_hand)
                uc_name = card_name(upcard_cid)
                improvement = dw - dw_with
                nm_val = near_meld_value(upcard_cid, hand)
                if improvement > 0 or nm_val >= 4:
                    return 52, f"Upcard {uc_name} {'reduces deadwood by ' + str(improvement) if improvement > 0 else 'has strong meld connections (value ' + str(nm_val) + ')'}. Taking it improves hand [{hand_str}] toward a knockable position."
                else:
                    return 54, f"Upcard {uc_name} doesn't reduce deadwood ({dw}) or connect to existing melds. Passing avoids revealing card preferences to opponent."
            return 54, f"Passing on unclear upcard. Current hand has {len(melds)} melds and {dw} deadwood."

        if has_draw_upcard and has_draw_stock:
            if upcard_cid is not None:
                test_hand = hand + [upcard_cid]
                dw_with, _ = calc_deadwood(test_hand)
                uc_name = card_name(upcard_cid)
                improvement = dw - dw_with
                nm_val = near_meld_value(upcard_cid, hand)
                if improvement >= 3 or nm_val >= 6:
                    return 52, f"Taking upcard {uc_name} — it {'drops deadwood from ' + str(dw) + ' to ' + str(dw_with) if improvement > 0 else 'has excellent meld potential (near-meld ' + str(nm_val) + ')'}. Worth the information reveal."
                else:
                    return 53, f"Upcard {uc_name} offers minimal improvement (deadwood {dw}→{dw_with if improvement > 0 else dw}). Drawing blind from stock preserves information advantage."
            return 53, f"Drawing from stock. {len(melds)} melds formed, {dw} deadwood. Blind draw may find the missing piece."

        if has_draw_stock:
            return 53, f"Drawing from stock with {len(melds)} melds and {dw} deadwood."
        return 52, f"Taking upcard as only draw option."

    # Discard
    if discard_actions:
        non_melded = [a for a in discard_actions if a not in melded]
        if non_melded:
            def priority(cid):
                return deadwood_value(cid) * 2 - near_meld_value(cid, hand)
            worst = max(non_melded, key=priority)
            cn = card_name(worst)
            dw_val = deadwood_value(worst)
            nm_val = near_meld_value(worst, hand)
            remaining = [c for c in hand if c != worst]
            new_dw, _ = calc_deadwood(remaining)
            if nm_val <= 1:
                think = f"Discarding {cn} (deadwood {dw_val}) — completely isolated, no adjacent ranks in same suit and no rank matches. Deadwood {dw}→{new_dw}."
            else:
                think = f"Discarding {cn} (deadwood {dw_val}, near-meld value {nm_val}). Despite some connections, the high deadwood cost makes it the best discard. {dw}→{new_dw} deadwood."
            return worst, think
        else:
            worst = min(discard_actions, key=deadwood_value)
            cn = card_name(worst)
            return worst, f"All cards form melds — sacrificing {cn} (value {deadwood_value(worst)}) to draw for potential improvement."

    return legal[0], "Taking available action."
